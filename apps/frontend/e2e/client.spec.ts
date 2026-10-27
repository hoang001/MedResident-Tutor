import {test, expect} from "@playwright/test";
import {parseApiError, safeReturnPath} from "../lib/api";
test("client handles detail string, validation list and business code safely", () => {
  expect(parseApiError(409, {detail: "Conflict"}).code).toBe("HTTP_409");
  expect(parseApiError(422, {detail: [{loc:["body","email"], type:"value_error", msg:"unsafe", input:"SECRET"}]}).fields.email).toBe("Địa chỉ email không hợp lệ.");
  expect(parseApiError(401, {error: {code:"INVALID_CREDENTIALS", message:"wrong"}}).kind).toBe("authentication");
  expect(parseApiError(500, {detail: "SECRET"}).message).not.toContain("SECRET");
});
test("return path accepts internal routes and rejects unsafe targets/loops", () => {
  expect(safeReturnPath("/learn?attempt=abc")).toBe("/learn?attempt=abc");
  for (const path of ["https://outside.invalid", "//outside.invalid", "/\\outside.invalid", "/login", "/register", "/%5coutside.invalid"]) expect(safeReturnPath(path)).toBe("/learn");
});
