import { Component, ReactNode } from "react";
import { ErrorState } from "./ErrorState";

/** Keeps a page that fails to draw from taking Steam's window with it. */
export class Guard extends Component<{ what: string; children: ReactNode }, { error?: string }> {
  state: { error?: string } = {};
  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
  render() {
    if (this.state.error !== undefined) {
      return <ErrorState title={`Couldn't open ${this.props.what}`} detail={this.state.error} retry={{ run: () => this.setState({ error: undefined }) }} />;
    }
    return this.props.children;
  }
}
