import hashlib
import io
import os
import re
import subprocess
import tarfile

import pytest

from boilerromm import releases
from boilerromm.emulators import Layout
from boilerromm.emulators.kyty import RUN, TAG, Kyty
from boilerromm.install import Target

ASSET = f"{TAG}-Linux-x86_64.tar.gz"
ASSET_URL = f"https://github.com/KytyPS5/KytyPS5/releases/download/{TAG}/{ASSET}"
EMULATOR = b"\x7fELF" + b"e" * 100


def build(members=None):
    """A release archive laid out as the project's: everything under ./, launcher and updater included."""
    members = members if members is not None else {
        "kyty_emulator": EMULATOR, "kyty_launcher": b"launcher", "kyty_updater": b"updater", "qt.conf": b"[Paths]",
        "assets/fonts/NotoSans-Regular.ttf": b"font", "assets/sounds/trophy-unlock.wav": b"wav",
        "lib/libQt6Core.so.6": b"qt", "licenses/ffmpeg/LICENSE": b"licence",
    }
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        folder = tarfile.TarInfo("./")
        folder.type = tarfile.DIRTYPE
        tar.addfile(folder)
        for name, content in members.items():
            info = tarfile.TarInfo("./" + name)
            info.size = len(content)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(content))
        link = tarfile.TarInfo("./assets/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    return out.getvalue()


class FakeResponse:
    def __init__(self, status, body=None):
        self.status = status
        self._body = body
        self.content = self

    async def json(self):
        return self._body

    async def iter_chunked(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeGitHub:
    def __init__(self, archive=None, assets=None):
        self.archive = archive if archive is not None else build()
        sha = "sha256:" + hashlib.sha256(self.archive).hexdigest()
        self.release = {"tag_name": TAG, "name": TAG, "assets": assets if assets is not None else [
            {"name": f"{TAG}-Windows-x64.zip", "size": 1, "digest": None, "browser_download_url": "https://x/win"},
            {"name": f"{TAG}-macOS-x86_64.zip", "size": 1, "digest": None, "browser_download_url": "https://x/mac"},
            {"name": ASSET, "size": len(self.archive), "digest": sha, "browser_download_url": ASSET_URL},
        ]}

    def get(self, url, headers=None):
        if url == f"{releases.API}/repos/KytyPS5/KytyPS5/releases/tags/{TAG}":
            return FakeResponse(200, self.release)
        if url == ASSET_URL:
            return FakeResponse(200, self.archive)
        return FakeResponse(404, {})


@pytest.fixture
def kyty(tmp_path):
    return Kyty(Layout(str(tmp_path)))


def write(path, content=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return str(path)


def test_the_build_is_the_pinned_linux_archive():
    assert Kyty.source.repo == "KytyPS5/KytyPS5" and Kyty.source.tag == TAG
    assert re.fullmatch(r"KytyPS5-\d{4}-\d{2}-\d{2}-[0-9a-f]{7}", TAG)
    assert re.search(Kyty.source.asset, ASSET)
    assert not re.search(Kyty.source.asset, f"{TAG}-Windows-x64.zip")
    assert not re.search(Kyty.source.asset, f"{TAG}-macOS-x86_64.zip")


def test_a_build_is_named_by_its_day_and_commit(kyty):
    assert kyty.version_label(TAG, TAG) == TAG.removeprefix("KytyPS5-")


def test_it_needs_nothing_from_a_real_console(kyty):
    assert kyty.firmware_ready() and kyty.firmware_found() == []


async def test_install_takes_the_emulator_and_its_assets_out_of_the_archive(kyty):
    assert await kyty.install(FakeGitHub()) == TAG
    build_dir = os.path.join(kyty.home, "build")
    assert kyty.executable == os.path.join(build_dir, "kyty_emulator")
    with open(kyty.executable, "rb") as f:
        assert f.read() == EMULATOR
    assert os.access(kyty.executable, os.X_OK)
    assert sorted(os.listdir(build_dir)) == ["assets", "kyty_emulator"]
    assert os.path.isfile(os.path.join(build_dir, "assets", "fonts", "NotoSans-Regular.ttf"))
    assert os.path.isfile(os.path.join(build_dir, "assets", "sounds", "trophy-unlock.wav"))
    assert not os.path.lexists(os.path.join(build_dir, "assets", "link"))
    assert kyty.version == TAG and kyty.version_name == TAG.removeprefix("KytyPS5-") and kyty.status()["installed"]
    assert os.listdir(kyty.cache_dir) == []


async def test_installing_again_replaces_the_build(kyty):
    await kyty.install(FakeGitHub())
    write(os.path.join(kyty.build_dir, "stale"), b"old")
    await kyty.install(FakeGitHub(build({"kyty_emulator": b"\x7fELFnew"})))
    assert os.listdir(kyty.build_dir) == ["kyty_emulator"]
    with open(kyty.executable, "rb") as f:
        assert f.read() == b"\x7fELFnew"


@pytest.mark.parametrize("github, message", [
    (FakeGitHub(build({"kyty_launcher": b"only the launcher"})), "holds no kyty_emulator"),
    (FakeGitHub(b"not an archive at all" * 10), "damaged"),
    (FakeGitHub(assets=[]), "no asset"),
])
async def test_an_archive_that_cannot_be_used_installs_nothing(kyty, github, message):
    with pytest.raises(releases.ReleaseError, match=message):
        await kyty.install(github)
    assert kyty.version == ""
    assert not os.path.exists(kyty.build_dir) and not os.path.exists(kyty.build_dir + ".part")
    assert not os.path.exists(os.path.join(kyty.cache_dir, "kyty.tar.gz"))


async def test_a_failed_update_keeps_the_build_that_works(kyty):
    await kyty.install(FakeGitHub())
    with pytest.raises(releases.ReleaseError):
        await kyty.install(FakeGitHub(b"broken" * 10))
    assert kyty.version == TAG and os.path.isfile(kyty.executable)


async def test_uninstall_removes_the_build_and_keeps_the_saves(kyty, tmp_path):
    await kyty.install(FakeGitHub())
    kyty.prepare()
    save = write(tmp_path / "saves" / "ps5" / "kyty" / "PPSA00001" / "sdimg", b"save")
    kyty.uninstall()
    assert not os.path.exists(kyty.build_dir) and kyty.version == ""
    assert os.path.exists(save)


def test_saves_and_the_shader_cache_are_linked_into_the_folder_it_runs_in(kyty, tmp_path):
    kyty.prepare()
    assert os.readlink(os.path.join(kyty.data_dir, "_SaveData")) == str(tmp_path / "saves" / "ps5" / "kyty")
    pipelines = os.path.join(kyty.cache_dir, "pipelines")
    assert os.readlink(os.path.join(kyty.data_dir, "_PipelineCache")) == pipelines and os.path.isdir(pipelines)
    write(os.path.join(kyty.data_dir, "_SaveData", "PPSA00001", "sdimg"), b"save")
    assert (tmp_path / "saves" / "ps5" / "kyty" / "PPSA00001" / "sdimg").read_bytes() == b"save"


def test_saves_it_already_wrote_are_moved_not_lost_and_prepare_can_repeat(kyty, tmp_path):
    write(os.path.join(kyty.data_dir, "_SaveData", "PPSA00001", "sdimg"), b"mine")
    kyty.prepare()
    kyty.prepare()
    assert os.path.islink(os.path.join(kyty.data_dir, "_SaveData"))
    assert (tmp_path / "saves" / "ps5" / "kyty" / "PPSA00001" / "sdimg").read_bytes() == b"mine"


def test_reset_config_leaves_the_saves(kyty, tmp_path):
    kyty.prepare()
    save = write(os.path.join(kyty.data_dir, "_SaveData", "PPSA00001", "sdimg"), b"save")
    kyty.reset_config()
    assert os.path.exists(save) and (tmp_path / "saves" / "ps5" / "kyty" / "PPSA00001" / "sdimg").exists()


def test_command_starts_the_game_fullscreen_from_the_data_folder(kyty):
    c = kyty.command("/roms/ps5/Game [PPSA00001]")
    assert c.argv == ["/bin/sh", "-c", RUN, kyty.executable, kyty.data_dir,
                      "--game", "/roms/ps5/Game [PPSA00001]", "--fullscreen", "--hide-cursor", "--shader-cache"]
    assert c.env == {"XDG_CONFIG_HOME": kyty.config_dir, "XDG_DATA_HOME": kyty.data_dir, "XDG_CACHE_HOME": kyty.cache_dir}


def test_command_runs_the_emulator_in_the_data_folder_with_the_game_as_given(kyty, tmp_path):
    kyty.prepare()
    log = tmp_path / "call"
    write(kyty.executable, f'#!/bin/sh\npwd > "{log}"\nfor a in "$@"; do echo "$a" >> "{log}"; done\n'.encode())
    os.chmod(kyty.executable, 0o755)
    subprocess.run(kyty.command("/roms/ps5/my game.zar").argv, check=True, cwd=tmp_path)
    assert log.read_text().splitlines() == [kyty.data_dir, "--game", "/roms/ps5/my game.zar", "--fullscreen",
                                            "--hide-cursor", "--shader-cache"]


def test_launch_file_is_a_single_file_as_it_is(kyty, tmp_path):
    assert kyty.launch_file(Target(str(tmp_path / "Game.zar"), False)) == str(tmp_path / "Game.zar")


def test_launch_file_is_the_folder_that_holds_an_eboot(kyty, tmp_path):
    direct = tmp_path / "Direct"
    write(direct / "eboot.bin", b"x")
    write(direct / "sce_sys" / "param.json", b"{}")
    assert kyty.launch_file(Target(str(direct), True)) == str(direct)

    nested = tmp_path / "Nested [PPSA00001]"
    write(nested / "readme.txt", b"x" * 50)
    write(nested / "PPSA00001" / "EBOOT.BIN", b"x")
    assert kyty.launch_file(Target(str(nested), True)) == str(nested / "PPSA00001")

    deeper = tmp_path / "Deeper"
    write(deeper / "a" / "b" / "eboot.bin", b"x")
    assert kyty.launch_file(Target(str(deeper), True)) == str(deeper / "a" / "b")
    too_deep = tmp_path / "TooDeep"
    write(too_deep / "a" / "b" / "c" / "eboot.bin", b"x")
    assert kyty.launch_file(Target(str(too_deep), True)) == str(too_deep)


def test_launch_file_is_a_zarchive_dump_in_the_folder(kyty, tmp_path):
    dump = tmp_path / "Dump"
    write(dump / "notes.txt", b"x" * 500)
    write(dump / "Game.ZAR", b"x" * 10)
    assert kyty.launch_file(Target(str(dump), True)) == str(dump / "Game.ZAR")

    both = tmp_path / "Both"
    write(both / "eboot.bin", b"x")
    write(both / "Game.zar", b"x")
    assert kyty.launch_file(Target(str(both), True)) == str(both)


def test_launch_file_falls_back_to_the_largest_file_of_a_folder_with_no_game_in_it(kyty, tmp_path):
    odd = tmp_path / "Odd"
    write(odd / "small.txt", b"x")
    write(odd / "game.elf", b"x" * 100)
    assert kyty.launch_file(Target(str(odd), True)) == str(odd / "game.elf")
    assert kyty.launch_file(Target(str(tmp_path / "missing"), True)) == str(tmp_path / "missing")
