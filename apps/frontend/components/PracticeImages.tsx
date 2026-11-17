"use client";
import Image from "next/image";
import {useEffect, useRef, useState} from "react";
import {clearToken, getToken, loginRedirect} from "@/lib/api";
import {ClinicalExercise, ClinicalImage, ClinicalSolution} from "@/lib/practice-types";

function ProtectedImage({image, grid, annotations}: {image: ClinicalImage; grid: boolean; annotations: ClinicalSolution["annotations"]}) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const [zoomed, setZoomed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    const timer = setTimeout(() => {setError(true); controller.abort();}, 30000);
    async function load() {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}${image.url}`, {headers: {Authorization: `Bearer ${getToken()}`}, signal: controller.signal, cache: "no-store"});
        if (response.status === 401) {clearToken(); loginRedirect("expired"); return;}
        if (!response.ok) throw new Error("image unavailable");
        const blob = await response.blob();
        if (!controller.signal.aborted) {objectUrl = URL.createObjectURL(blob); setSrc(objectUrl);}
      } catch {if (!controller.signal.aborted) setError(true);}
      finally {clearTimeout(timer);}
    }
    void load();
    return () => {controller.abort(); clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl);};
  }, [image.url, revision]);
  function canvas() {return <div className="practice-image-canvas">
    <Image unoptimized src={src} alt={image.alt} width={image.width} height={image.height} data-testid="clinical-image"/>
    {(grid || annotations.length > 0) && <svg className="practice-image-overlay" viewBox={`0 0 ${image.width} ${image.height}`} aria-label={annotations.length ? "Vùng chú giải nguồn sau khi nộp" : "Lưới định vị 3 nhân 3"} role="img">
      {grid && [1,2].map(n => <g key={n}><line x1={image.width*n/3} x2={image.width*n/3} y1={0} y2={image.height} stroke="white" strokeWidth={1.5} strokeDasharray="8 8"/><line x1={0} x2={image.width} y1={image.height*n/3} y2={image.height*n/3} stroke="white" strokeWidth={1.5} strokeDasharray="8 8"/></g>)}
      {grid && [1,2,3].flatMap(r => [1,2,3].map(c => <text key={`${r}-${c}`} x={(c-1)*image.width/3+8} y={(r-1)*image.height/3+24} fill="white" stroke="black" paintOrder="stroke" strokeWidth={2} fontSize={18}>{r},{c}</text>))}
      {annotations.map((a,i) => <rect key={i} x={a.box.xmin} y={a.box.ymin} width={a.box.xmax-a.box.xmin} height={a.box.ymax-a.box.ymin} fill="none" stroke="#ffcd38" strokeWidth={4} data-testid="answer-annotation"/>)}
    </svg>}
  </div>;}
  return <figure className="practice-image">
    {error ? <p role="alert">Không tải được ảnh. <button type="button" className="secondary" onClick={() => {setError(false); setSrc(""); setRevision(x => x + 1);}}>Tải lại ảnh</button></p> : !src ? <p role="status">Đang tải {image.alt.toLowerCase()}…</p> : <>
      {canvas()}
      <><button type="button" className="secondary" onClick={() => {setZoomed(true); dialog.current?.showModal();}}>Xem ảnh lớn{grid ? " với lưới" : ""}</button>
        <dialog ref={dialog} className="practice-zoom" aria-label={`Xem lớn ${image.alt.toLowerCase()}`} onClose={() => setZoomed(false)} onClick={e => {if (e.target === dialog.current) dialog.current.close();}}>
          <button type="button" onClick={() => dialog.current?.close()}>Đóng ảnh lớn</button>{grid&&<p>Hàng từ trên xuống, cột từ trái sang; nhãn ô là hàng,cột.</p>}{zoomed && src && canvas()}
        </dialog></>
      <a href={src} target="_blank" rel="noopener noreferrer">Mở {image.alt.toLowerCase()} ở kích thước gốc</a>
    </>}
    <figcaption>{image.alt}{grid ? " · Lưới 3×3 tính theo ảnh hiển thị" : ""}</figcaption>
  </figure>;
}

export function PracticeImages({exercise, solution}: {exercise: ClinicalExercise; solution?: ClinicalSolution}) {
  return <div className="practice-images">{exercise.images.map((image,index) => <ProtectedImage key={image.asset_id + image.url} image={image} grid={exercise.show_grid && index === 0} annotations={solution?.annotations.filter(a => a.asset_id === image.asset_id) ?? []}/>)}</div>;
}
