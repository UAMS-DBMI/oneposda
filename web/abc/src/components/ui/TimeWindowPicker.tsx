import { TIME_WINDOWS, type TimeWindow } from "../../lib/timeWindow";
import { SegmentedControl } from "./SegmentedControl";

/** "In the last 1h / 6h / … / all": one click instead of typing an interval. */
export function TimeWindowPicker({
  value,
  onChange,
  label = "Time window",
}: {
  value: TimeWindow;
  onChange: (value: TimeWindow) => void;
  label?: string;
}) {
  return (
    <SegmentedControl
      label={label}
      options={TIME_WINDOWS}
      value={value}
      onChange={onChange}
    />
  );
}
