import { describe, expect, test } from "bun:test";
import { PyFloat, pyJson, pyFloatString } from "../src/pyjson";

describe("pyFloatString", () => {
  test("integral floats keep .0", () => {
    expect(pyFloatString(0)).toBe("0.0");
    expect(pyFloatString(1)).toBe("1.0");
    expect(pyFloatString(-3)).toBe("-3.0");
  });
  test("fractional floats print shortest form", () => {
    expect(pyFloatString(1.5)).toBe("1.5");
    expect(pyFloatString(0.078987)).toBe("0.078987");
  });
  test("non-finite becomes null", () => {
    expect(pyFloatString(NaN)).toBe("null");
    expect(pyFloatString(Infinity)).toBe("null");
  });
});

describe("pyJson", () => {
  test("PyFloat serializes Python-style", () => {
    expect(pyJson(new PyFloat(0))).toBe("0.0");
    expect(pyJson([new PyFloat(2), 2])).toBe("[2.0,2]");
  });
  test("plain integers stay integers", () => {
    expect(pyJson(42)).toBe("42");
  });
  test("plain non-integral numbers are floats", () => {
    expect(pyJson(1.25)).toBe("1.25");
  });
  test("objects preserve insertion order", () => {
    expect(pyJson({ b: 1, a: null, c: "x" })).toBe('{"b":1,"a":null,"c":"x"}');
  });
  test("no HTML escaping", () => {
    expect(pyJson("<a>&'")).toBe('"<a>&\'"');
  });
  test("nested structures", () => {
    expect(pyJson({ x: [true, false, { y: new PyFloat(1) }] })).toBe(
      '{"x":[true,false,{"y":1.0}]}',
    );
  });
  test("bigint", () => {
    expect(pyJson(9007199254740993n)).toBe("9007199254740993");
  });
});
