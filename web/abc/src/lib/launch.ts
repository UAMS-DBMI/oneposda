import type { LaunchPreview, ResolvedArg } from "../api/types";

/** Client-side mirror of the server's expand_command for the live preview. */
export function expandCommand(commandLine: string, values: Record<string, string>): string {
  let expanded = commandLine;
  for (const [name, value] of Object.entries(values)) {
    expanded = expanded.split(`<${name}>`).join(value ?? "");
  }
  return expanded;
}

export function initialValues(preview: LaunchPreview): Record<string, string> {
  return Object.fromEntries(
    Object.entries(preview.args).map(([name, arg]) => [name, arg.value]),
  );
}

export function sourceLabel(arg: ResolvedArg, edited: boolean): string {
  return edited ? "entered" : arg.source;
}
