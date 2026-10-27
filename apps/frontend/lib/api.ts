export type ErrorKind = "network" | "authentication" | "validation" | "processing";
export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = "NETWORK_ERROR", public kind: ErrorKind = "network", public fields: Record<string, string> = {}) { super(message); this.name = "ApiError"; }
}
export function getToken(): string | null { return typeof window === "undefined" ? null : localStorage.getItem("access_token"); }
export function saveToken(token: string): void {
  localStorage.setItem("access_token", token);
  window.dispatchEvent(new Event("auth-changed"));
}
export function clearToken(): void {
  localStorage.removeItem("access_token");
  window.dispatchEvent(new Event("auth-changed"));
}
export function safeReturnPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\x00-\x20]|%5c|%0[ad]/i.test(value)) return "/learn";
  const url = new URL(value, "http://internal.invalid");
  let path: string;
  try {path = decodeURIComponent(url.pathname).replace(/\/$/, "") || "/";} catch {return "/learn";}
  if (url.origin !== "http://internal.invalid" || !["/", "/learn", "/dashboard", "/exams", "/progress", "/admin/documents", "/admin/questions"].includes(path)) return "/learn";
  return path + url.search + url.hash;
}
let redirecting = false;
export function loginRedirect(reason = "required"): void {
  if (window.location.pathname === "/login" || redirecting) return;
  redirecting = true;
  const next = safeReturnPath(window.location.pathname + window.location.search);
  window.location.replace(`/login?reason=${encodeURIComponent(reason)}&next=${encodeURIComponent(next)}`);
}
export function logout(): void { clearToken(); window.location.assign("/login?reason=logout"); }

function validationFields(details: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (!Array.isArray(details)) return result;
  for (const item of details) {
    if (!item || !Array.isArray(item.loc)) continue;
    const field = String(item.loc.at(-1));
    result[field] = field === "email" ? "Địa chỉ email không hợp lệ." : item.type === "missing" ? "Vui lòng điền trường này." : item.type === "string_too_long" ? "Nội dung vượt quá giới hạn cho phép." : "Giá trị không hợp lệ.";
  }
  return result;
}
export function parseApiError(status: number, body: unknown): ApiError {
  const data = body && typeof body === "object" ? body as {error?: {code?: string; message?: string; details?: unknown}; detail?: unknown} : {};
  const fields = validationFields(data.error?.details ?? data.detail);
  const code = data.error?.code ?? `HTTP_${status}`;
  let message = data.error?.message ?? (typeof data.detail === "string" ? data.detail : "Không thể xử lý yêu cầu.");
  if (status >= 500) message = "Dịch vụ đang gặp lỗi. Bạn có thể thử lại sau.";
  if (status === 422) message = "Vui lòng kiểm tra các trường đã nhập.";
  if (status === 401) message = "Email hoặc mật khẩu không đúng, hoặc phiên đăng nhập đã hết hạn.";
  if (status === 403) message = "Bạn không có quyền thực hiện thao tác này.";
  if (status === 404) message = "Không tìm thấy dữ liệu hoặc bạn không có quyền truy cập.";
  if (status === 409) message = "Yêu cầu xung đột với dữ liệu đã lưu. Hãy mở kết quả hoặc tạo lượt mới.";
  if (code === "EMAIL_ALREADY_REGISTERED") message = "Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng email khác.";
  if (code === "GOOGLE_EMAIL_EXISTS") message = "Email này đã có tài khoản. Vui lòng đăng nhập bằng mật khẩu hiện có.";
  if (code === "GOOGLE_NOT_CONFIGURED") message = "Đăng nhập Google chưa được cấu hình.";
  return new ApiError(message, status, code, status === 401 ? "authentication" : status === 422 ? "validation" : "processing", fields);
}
export function errorMessage(error: unknown): string { return error instanceof ApiError ? error.message : "Không thể hoàn tất thao tác. Vui lòng thử lại."; }

export async function apiRequest<T>(path: string, init: RequestInit = {}, options: {timeoutMs?: number; redirectOn401?: boolean} = {}): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) throw new ApiError("Chưa cấu hình địa chỉ backend.", 0, "API_NOT_CONFIGURED", "processing");
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 45000);
  const abort = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener("abort", abort, {once: true});
  let response: Response;
  let body: unknown;
  try {
    response = await fetch(`${base}${path}`, {...init, headers, signal: controller.signal, cache: "no-store"});
    const text = await response.text();
    try {body = JSON.parse(text);} catch {body = null;}
  }
  catch {
    const pending = path === "/practice/attempts" && init.method === "POST" ? " Lần nộp đang chờ được giữ lại; gửi lại sẽ dùng cùng key." : "";
    throw new ApiError("Mất kết nối hoặc hết thời gian chờ. Vui lòng kiểm tra kết nối rồi thử lại." + pending);
  }
  finally { clearTimeout(timer); init.signal?.removeEventListener("abort", abort); }
  if (!response.ok) {
    const error = parseApiError(response.status, body);
    if (response.status === 401 && !["/auth/login", "/auth/register"].includes(path) && options.redirectOn401 !== false) {
      clearToken(); loginRedirect("expired");
    }
    throw error;
  }
  if (body === null) throw new ApiError("Backend trả dữ liệu không hợp lệ.", 502, "INVALID_RESPONSE", "processing");
  return body as T;
}
