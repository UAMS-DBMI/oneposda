// Package dicom ports the small amount of image-geometry math from
// papi/util/models.py, roi.py and roimath.py: slice ordering by
// projected position and the ROI contour coordinate transform.
package dicom

import (
	"sort"
	"strconv"
	"strings"
)

// ImageFile mirrors models.File: one DICOM file plus the geometry
// needed to order slices within a series.
type ImageFile struct {
	FileID      int64
	Path        string
	ImageType   []string
	FrameCount  int64
	Orientation []float64 // iop, 6 values
	Position    []float64 // ipp, 3 values
}

// ParseBackslashFloats parses a DICOM multi-value string like
// "1\0\0\0\1\0" into floats. Empty input produces an empty slice.
func ParseBackslashFloats(s string) ([]float64, error) {
	if s == "" {
		return []float64{}, nil
	}
	parts := strings.Split(s, `\`)
	out := make([]float64, len(parts))
	for i, p := range parts {
		f, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		if err != nil {
			return nil, err
		}
		out[i] = f
	}
	return out, nil
}

// NewImageFile mirrors File.from_raw. Unparseable iop/ipp values are an
// error, matching the Python float() conversion raising.
func NewImageFile(fileID int64, path, imageType string, numFrames int64, iop, ipp string) (ImageFile, error) {
	f := ImageFile{
		FileID:     fileID,
		Path:       path,
		FrameCount: numFrames,
		ImageType:  []string{},
	}
	if imageType != "" {
		f.ImageType = strings.Split(imageType, `\`)
	}
	var err error
	if f.Orientation, err = ParseBackslashFloats(iop); err != nil {
		return f, err
	}
	if f.Position, err = ParseBackslashFloats(ipp); err != nil {
		return f, err
	}
	return f, nil
}

// normal computes the slice normal from the orientation vectors.
func (f ImageFile) normal() [3]float64 {
	x := f.Orientation[:3]
	y := f.Orientation[3:]
	return [3]float64{
		x[1]*y[2] - x[2]*y[1],
		x[2]*y[0] - x[0]*y[2],
		x[0]*y[1] - x[1]*y[0],
	}
}

// ProjectedPosition projects the slice position onto the normal.
func (f ImageFile) ProjectedPosition() float64 {
	n := f.normal()
	return f.Position[0]*n[0] + f.Position[1]*n[1] + f.Position[2]*n[2]
}

// Consistent mirrors models.consistent: it sorts slices by projected
// position and guesses whether the set is volumetric. Fewer than two
// slices, or any slice missing geometry, means non-volumetric (and the
// input order is preserved).
func Consistent(files []ImageFile) ([]ImageFile, bool) {
	if len(files) < 2 {
		return files, false
	}
	for _, f := range files {
		if len(f.Orientation) < 6 || len(f.Position) < 3 {
			return files, false
		}
	}
	sorted := make([]ImageFile, len(files))
	copy(sorted, files)
	sort.SliceStable(sorted, func(i, j int) bool {
		return sorted[i].ProjectedPosition() < sorted[j].ProjectedPosition()
	})
	return sorted, true
}

// Matrix4 is a 4x4 transform applied as rowVector · M.
type Matrix4 [4][4]float64

// MakeTransform ports roimath.make_transform: build the patient->pixel
// transform from an ImageOrientationPatient (6 values) and
// ImagePositionPatient (3 values).
func MakeTransform(iop, ipp []float64) Matrix4 {
	x := [3]float64{iop[0], iop[1], iop[2]}
	y := [3]float64{iop[3], iop[4], iop[5]}
	z := [3]float64{
		x[1]*y[2] - x[2]*y[1],
		x[2]*y[0] - x[0]*y[2],
		x[0]*y[1] - x[1]*y[0],
	}

	// The Python code builds rows x/y/z then transposes, giving axes
	// as columns.
	var m Matrix4
	for i := range 3 {
		m[i][0] = x[i]
		m[i][1] = y[i]
		m[i][2] = z[i]
	}
	m[3][3] = 1

	// Rotate the ipp through the transform, then replace the bottom row
	// with its negation (the translation that zeroes the z coordinate).
	ipp4 := [4]float64{ipp[0], ipp[1], ipp[2], 1}
	rot := applyRow(ipp4, m)
	for j := range 3 {
		m[3][j] = -rot[j]
	}
	m[3][3] = -rot[3] // rot[3] is 1, matching xform.A[3] = -rot_ipp.A[0]

	return m
}

func applyRow(p [4]float64, m Matrix4) [4]float64 {
	var out [4]float64
	for j := range 4 {
		out[j] = p[0]*m[0][j] + p[1]*m[1][j] + p[2]*m[2][j] + p[3]*m[3][j]
	}
	return out
}

// TransformContour ports roi.get_transformed_contour's math: transform
// patient-space points to pixel coordinates, apply pixel spacing, and
// truncate to ints (numpy astype(int) truncates toward zero).
func TransformContour(points [][4]float64, xform Matrix4, pixelSpacing []float64) [][2]int64 {
	out := make([][2]int64, len(points))
	for i, p := range points {
		t := applyRow(p, xform)
		out[i] = [2]int64{
			int64(t[0] / pixelSpacing[0]),
			int64(t[1] / pixelSpacing[1]),
		}
	}
	return out
}

// ParseContourPoints parses raw contour data ("x\y\z\x\y\z\...") into
// homogeneous 4-vectors. The point count must be divisible by 3.
func ParseContourPoints(data string) ([][4]float64, error) {
	vals, err := ParseBackslashFloats(strings.TrimSpace(data))
	if err != nil {
		return nil, err
	}
	if len(vals)%3 != 0 {
		return nil, errNot3D
	}
	out := make([][4]float64, len(vals)/3)
	for i := range out {
		out[i] = [4]float64{vals[i*3], vals[i*3+1], vals[i*3+2], 1}
	}
	return out, nil
}

type contourErr string

func (e contourErr) Error() string { return string(e) }

const errNot3D = contourErr("contour is not in 3d space")

// FormatColor ports roi.format_color: "r\g\b" to a [r,g,b] triple,
// defaulting to black when missing or malformed.
func FormatColor(color string) [3]int64 {
	if color == "" {
		return [3]int64{0, 0, 0}
	}
	parts := strings.Split(color, `\`)
	if len(parts) != 3 {
		return [3]int64{0, 0, 0}
	}
	var out [3]int64
	for i, p := range parts {
		n, err := strconv.ParseInt(strings.TrimSpace(p), 10, 64)
		if err != nil {
			return [3]int64{0, 0, 0}
		}
		out[i] = n
	}
	return out
}
