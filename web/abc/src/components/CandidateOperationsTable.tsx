import type { Candidate } from "../api/types";
import { EmptyState } from "./ui";

/** "This spreadsheet has no Operation": operations whose fields it can supply. */
export function CandidateOperationsTable({
  candidates,
  onChoose,
}: {
  candidates: Candidate[];
  onChoose: (operationName: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="table-grid">
        <thead>
          <tr>
            <th>operation</th>
            <th>command</th>
            <th>input line format</th>
            <th className="num" title="columns the operation can take from this data">matches</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {candidates.map(({ operation, matches }) => (
            <tr key={operation.operation_name}>
              <td className="whitespace-nowrap font-medium">{operation.operation_name}</td>
              <td className="mono max-w-md truncate" title={operation.command_line}>{operation.command_line}</td>
              <td className="mono">{operation.input_line_format}</td>
              <td className="num">{matches}</td>
              <td className="text-right">
                <button type="button" className="btn-primary btn-sm" onClick={() => onChoose(operation.operation_name)}>
                  Choose
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {candidates.length === 0 && <EmptyState>No operation takes these columns as input.</EmptyState>}
    </div>
  );
}
