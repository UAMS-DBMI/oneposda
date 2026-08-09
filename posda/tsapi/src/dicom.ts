// Image-geometry math from papi/util/models.py, roi.py and roimath.py:
// slice ordering by projected position and the ROI contour coordinate
// transform.

/** One DICOM file plus the geometry needed to order slices. */
export interface ImageFile {
  fileId: number;
  path: string;
  imageType: string[];
  frameCount: number;
  orientation: number[]; // iop, 6 values
  position: number[]; // ipp, 3 values
}

/**
 * Parse a DICOM multi-value string like "1\0\0\0\1\0" into floats.
 * Empty input produces an empty array; unparseable values throw,
 * matching the Python float() conversion raising.
 */
export function parseBackslashFloats(s: string): number[] {
  if (s === "") return [];
  return s.split("\\").map((p) => {
    const t = p.trim();
    const f = Number(t);
    if (t === "" || (Number.isNaN(f) && !/^[+-]?nan$/i.test(t))) {
      throw new Error(`could not convert string to float: '${p}'`);
    }
    return f;
  });
}

/** Mirrors File.from_raw. */
export function newImageFile(
  fileId: number,
  path: string,
  imageType: string,
  numFrames: number,
  iop: string,
  ipp: string,
): ImageFile {
  return {
    fileId,
    path,
    frameCount: numFrames,
    imageType: imageType !== "" ? imageType.split("\\") : [],
    orientation: parseBackslashFloats(iop),
    position: parseBackslashFloats(ipp),
  };
}

function normal(orientation: number[]): [number, number, number] {
  const x = orientation.slice(0, 3);
  const y = orientation.slice(3);
  return [
    x[1]! * y[2]! - x[2]! * y[1]!,
    x[2]! * y[0]! - x[0]! * y[2]!,
    x[0]! * y[1]! - x[1]! * y[0]!,
  ];
}

/** Project the slice position onto the slice normal. */
export function projectedPosition(f: ImageFile): number {
  const n = normal(f.orientation);
  return f.position[0]! * n[0] + f.position[1]! * n[1] + f.position[2]! * n[2];
}

/**
 * Mirrors models.consistent: sort slices by projected position and
 * guess whether the set is volumetric. Fewer than two slices, or any
 * slice missing geometry, means non-volumetric (input order kept).
 */
export function consistent(files: ImageFile[]): [ImageFile[], boolean] {
  if (files.length < 2) return [files, false];
  for (const f of files) {
    if (f.orientation.length < 6 || f.position.length < 3) {
      return [files, false];
    }
  }
  const sorted = files
    .map((f, i) => ({ f, i }))
    .sort(
      (a, b) =>
        projectedPosition(a.f) - projectedPosition(b.f) || a.i - b.i,
    )
    .map((x) => x.f);
  return [sorted, true];
}

/** A 4x4 transform applied as rowVector · M. */
export type Matrix4 = number[][];

/**
 * Ports roimath.make_transform: build the patient->pixel transform
 * from an ImageOrientationPatient (6 values) and ImagePositionPatient
 * (3 values).
 */
export function makeTransform(iop: number[], ipp: number[]): Matrix4 {
  const x = [iop[0]!, iop[1]!, iop[2]!];
  const y = [iop[3]!, iop[4]!, iop[5]!];
  const z = [
    x[1]! * y[2]! - x[2]! * y[1]!,
    x[2]! * y[0]! - x[0]! * y[2]!,
    x[0]! * y[1]! - x[1]! * y[0]!,
  ];

  // The Python code builds rows x/y/z then transposes, giving axes as
  // columns.
  const m: Matrix4 = [
    [x[0]!, y[0]!, z[0]!, 0],
    [x[1]!, y[1]!, z[1]!, 0],
    [x[2]!, y[2]!, z[2]!, 0],
    [0, 0, 0, 1],
  ];

  // Rotate the ipp through the transform, then replace the bottom row
  // with its negation (the translation that zeroes the z coordinate).
  const rot = applyRow([ipp[0]!, ipp[1]!, ipp[2]!, 1], m);
  m[3] = [-rot[0]!, -rot[1]!, -rot[2]!, -rot[3]!];

  return m;
}

export function applyRow(p: number[], m: Matrix4): number[] {
  const out = [0, 0, 0, 0];
  for (let j = 0; j < 4; j++) {
    out[j] =
      p[0]! * m[0]![j]! +
      p[1]! * m[1]![j]! +
      p[2]! * m[2]![j]! +
      p[3]! * m[3]![j]!;
  }
  return out;
}

/**
 * Ports roi.get_transformed_contour's math: transform patient-space
 * points to pixel coordinates, apply pixel spacing, and truncate to
 * ints (numpy astype(int) truncates toward zero).
 */
export function transformContour(
  points: number[][],
  xform: Matrix4,
  pixelSpacing: number[],
): [number, number][] {
  return points.map((p) => {
    const t = applyRow(p, xform);
    return [
      Math.trunc(t[0]! / pixelSpacing[0]!),
      Math.trunc(t[1]! / pixelSpacing[1]!),
    ];
  });
}

/**
 * Parse raw contour data ("x\y\z\x\y\z\...") into homogeneous
 * 4-vectors. The value count must be divisible by 3.
 */
export function parseContourPoints(data: string): number[][] {
  const vals = parseBackslashFloats(data.trim());
  if (vals.length % 3 !== 0) {
    throw new Error("contour is not in 3d space");
  }
  const out: number[][] = [];
  for (let i = 0; i < vals.length / 3; i++) {
    out.push([vals[i * 3]!, vals[i * 3 + 1]!, vals[i * 3 + 2]!, 1]);
  }
  return out;
}

/**
 * Ports roi.format_color: "r\g\b" to a [r,g,b] triple, defaulting to
 * black when missing or malformed.
 */
export function formatColor(color: string | null): [number, number, number] {
  if (!color) return [0, 0, 0];
  const parts = color.split("\\");
  if (parts.length !== 3) return [0, 0, 0];
  const out: number[] = [];
  for (const p of parts) {
    const t = p.trim();
    if (!/^[+-]?\d+$/.test(t)) return [0, 0, 0];
    out.push(Number.parseInt(t, 10));
  }
  return out as [number, number, number];
}
