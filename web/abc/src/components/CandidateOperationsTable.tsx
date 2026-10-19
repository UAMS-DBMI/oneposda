import type { Candidate } from "../api/types";

/** "This spreadsheet has no Operation": operations whose fields it can supply. */
export function CandidateOperationsTable({
  candidates,
  onChoose,
}: {
  candidates: Candidate[];
  onChoose: (operationName: string) => void;
}) {
  return (
    <table className="table-grid">
      <caption className="py-1 text-left text-sm font-semibold">Available Operations</caption>
      <thead>
        <tr>
          <th>Operation</th>
          <th>Command Line</th>
          <th>Input Line Format</th>
          <th># matches</th>
          <th>Choose</th>
        </tr>
      </thead>
      <tbody>
        {candidates.length === 0 && (
          <tr>
            <td colSpan={5} className="text-gray-500">
              No operation takes these columns as input.
            </td>
          </tr>
        )}
        {candidates.map(({ operation, matches }) => (
          <tr key={operation.operation_name}>
            <td className="whitespace-nowrap">{operation.operation_name}</td>
            <td className="font-mono text-xs">{operation.command_line}</td>
            <td className="font-mono text-xs">{operation.input_line_format}</td>
            <td>{matches}</td>
            <td>
              <button type="button" className="btn" onClick={() => onChoose(operation.operation_name)}>
                Choose
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
