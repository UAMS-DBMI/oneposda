export function NotYetPage({ title, phase }: { title: string; phase: number }) {
  return (
    <div>
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-gray-600">
        This screen arrives in phase {phase} of the ABC replacement. Until then it is
        still available in the Perl application.
      </p>
    </div>
  );
}
