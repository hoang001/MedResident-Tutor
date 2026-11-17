"use client";

import {PageHeading} from "@/components/ui";
import {ResourceNav} from "@/components/ResourceNav";
import Link from "next/link";
import {useEffect, useState} from "react";
import {apiRequest, errorMessage} from "@/lib/api";
import {KnowledgeNode, nodeHref, useWorkspace} from "@/lib/knowledge";

type ScopeGroup = {group_id: string; title: string; round: number; year: number; choose: number; offered: number; required_credits: number; courses: {course_code: string; course_name: string}[]};
type Curriculum = {nodes: KnowledgeNode[]; study_scope: {groups: ScopeGroup[]; total_required_credits: number}};

export default function CurriculumPage() {
  const {user, error: authError} = useWorkspace();
  const [data, setData] = useState<Curriculum | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!user) return; let active = true;
    void apiRequest<Curriculum>("/knowledge/curriculum").then(d => {if (active) setData(d);}).catch(e => {if (active) setError(errorMessage(e));});
    return () => {active = false;};
  }, [user]);
  const course = data?.nodes.find(n => n.id === selected);
  const prior = data?.nodes.filter(n => n.type === "Course" && n.study_role === "prior_outcomes_only") ?? [];
  return <main className="container library"><PageHeading title="Khung chương trình" description="Tham khảo học phần và nguồn chương trình; nội dung từng môn cần giảng viên xác nhận."/><ResourceNav/>
    <p className="notice">Lộ trình dành cho bác sĩ nội trú đã học các học phần nền tảng. Round 2 học 4 môn bắt buộc; Round 3 chọn 4 trong 8 môn tự chọn. Tổng yêu cầu: 40 tín chỉ. Đề cương và bài học chi tiết vẫn chờ giảng viên xác nhận.</p>
    {(authError || error) && <p className="error" role="alert">{authError || error}</p>}
    {!data && !error && !authError && <p role="status">Đang tải chương trình…</p>}
    {data && <><div className="curriculum-layout"><section className="card wide"><h2>Học phần chuyên ngành</h2>
      {data.study_scope.groups.map(group => <section key={group.group_id} className="reader-section"><h3>{group.title}</h3><p className="muted">Năm {group.year} · {group.round === 2 ? `${group.offered} môn bắt buộc` : `Chọn ${group.choose}/${group.offered} môn`} · {group.required_credits} tín chỉ cần hoàn thành</p><ul className="curriculum-tree">
        {group.courses.map(spec => {const node = data.nodes.find(n => n.type === "Course" && n.study_role === "focus" && n.metadata.course_code === spec.course_code); return <li key={spec.course_code}>{node ? <button className={`course-choice ${selected === node.id ? "selected" : ""}`} onClick={() => setSelected(node.id)} aria-pressed={selected === node.id}>{node.title}<span className="muted">{spec.course_code} · {node.metadata.total_credits ?? (group.round === 2 ? 6 : 4)} tín chỉ</span></button> : <div className="requirement">{spec.course_name}<small>{spec.course_code} · Chưa có bản ghi học phần trong thư viện</small></div>}</li>;})}
      </ul></section>)}
      <p className="muted">Thứ tự trong danh sách theo ảnh chương trình; ảnh chưa quy định thứ tự học giữa các môn trong cùng Round.</p>
    </section>
      <section className="card wide course-panel" aria-live="polite">{course ? <><h2>{course.title}</h2><p className="helper">Mã học phần: {course.metadata.course_code}</p>
        <dl className="facts">{[["Năm học", course.metadata.year], ["Vòng học", course.metadata.round], ["Tín chỉ", course.metadata.total_credits]].filter(([, v]) => v !== undefined && v !== null && v !== "").map(([label, v]) => <div key={String(label)}><dt>{label}</dt><dd>{v}</dd></div>)}</dl>
        <p className="badge">Đang chờ nội dung từ giảng viên</p>
        {course.metadata.hmu_course_url && <p><a target="_blank" rel="noopener noreferrer" href={String(course.metadata.hmu_course_url)}>Xem học phần trên HMU LMS ↗</a><br/><small className="muted">Nội dung bài học trên LMS yêu cầu tài khoản do trường cấp.</small></p>}
        <p><Link href={nodeHref(course.id)}>Xem thông tin và bằng chứng nguồn</Link></p><h3>Nội dung tham khảo từ sách</h3>
        {course.suggested_topics?.length ? <><p className="muted">Phân nhóm tham khảo; chưa thay thế đề cương chính thức.</p>{course.suggested_topics.map((t, i) => <div className="content-block" key={i}><h4>{t.title}</h4>{t.source_ids.map(s => <p key={s}><Link href={`/knowledge?book=${s}&q=${encodeURIComponent(t.title.split(" ").slice(0, 3).join(" "))}`}>Tìm chủ đề trong {s === "SRC_ORTHO_EMERGENCY_001" ? "Cấp cứu ngoại khoa (2006)" : "Bệnh học ngoại khoa (2021)"}</Link> · <Link href={`/sources?id=${s}`}>Mục lục sách</Link></p>)}</div>)}</> : <p className="muted">Chưa có tài liệu được gắn với học phần này. Hệ thống giữ vị trí để bổ sung sau khi nhận đề cương.</p>}
      </> : <><h2>Nội dung học phần</h2><p>Chọn một môn chuyên ngành để xem thông tin và tài liệu tham khảo. Các môn đã học trước chỉ giữ yêu cầu đầu ra ở phần nền tảng bên dưới.</p></>}</section></div>
      <details className="card wide prior-outcomes"><summary>Nền tảng đầu vào — chỉ xem yêu cầu đầu ra</summary><p className="muted">Các học phần ở giai đoạn trước được giữ để đối chiếu nền tảng, không xếp thành bài học bắt buộc trên web. Đây là giả định về đối tượng sử dụng, không tự xác nhận từng học viên đã đạt năng lực.</p>
        <ul className="clean-list">{prior.sort((a, b) => String(a.metadata.course_code).localeCompare(String(b.metadata.course_code), "vi", {numeric: true})).map(n => <li key={n.id}><details><summary>{n.title} · {n.metadata.course_code}</summary><p>Chuẩn đầu ra riêng của học phần: <strong>đang chờ giảng viên cung cấp hoặc xác nhận</strong>.</p><p className="muted">Chuẩn đầu ra cấp chương trình ở dưới là nguồn tham khảo chung, chưa thay thế chuẩn của môn này.</p></details></li>)}</ul>
        {data.nodes.filter(n => n.type === "CurriculumRequirement").map(n => <p key={n.id}>{n.title}{n.metadata.required_level && <> · {String(n.metadata.required_level)}</>}</p>)}
      </details>
      <section className="card wide"><h2>Mục tiêu và chuẩn đầu ra cấp chương trình</h2><p className="muted">Các nội dung này áp dụng cho chương trình; chưa phải chuẩn đầu ra của từng môn.</p>
        {[["CurriculumObjective", "Mục tiêu"], ["CurriculumOutcome", "Chuẩn đầu ra"], ["CurriculumSource", "Nguồn HMU"]].map(([kind, title]) => <details key={kind}><summary>{title} ({data.nodes.filter(n => n.type === kind).length})</summary><ul className="clean-list">{data.nodes.filter(n => n.type === kind).sort((a, b) => a.title.localeCompare(b.title, "vi", {numeric: true})).map(n => <li key={n.id}><Link href={nodeHref(n.id)}>{n.title}</Link>{n.metadata.text && <p>{String(n.metadata.text)}</p>}</li>)}</ul></details>)}
      </section></>}
  </main>;
}
