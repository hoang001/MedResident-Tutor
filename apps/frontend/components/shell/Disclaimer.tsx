import { InfoIcon } from "@/components/shell/Icons";

export function Disclaimer() {
  return (
    <div className="disclaimer" role="note">
      <InfoIcon width={16} height={16} className="disclaimer-icon" />
      <p>
        Hệ thống chỉ hỗ trợ học tập và ôn luyện. Đây không phải công cụ chẩn đoán,
        điều trị hay hỗ trợ quyết định y khoa.
      </p>
    </div>
  );
}
