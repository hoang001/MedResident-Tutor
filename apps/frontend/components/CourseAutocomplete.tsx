"use client";
import {useEffect,useId,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {apiRequest,errorMessage} from "@/lib/api";
type Course={id:string;title:string;type:string;study_role?:string;metadata:{course_code?:string}};
const normalize=(text:string)=>text.normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/đ/g,"d").replace(/Đ/g,"D").toLowerCase();
export function CourseAutocomplete({id,value,onChange,disabled=false}:{id:string;value:string;onChange:(value:string)=>void;disabled?:boolean}) {
 const [courses,setCourses]=useState<Course[]>([]),[open,setOpen]=useState(false),[query,setQuery]=useState("");
 const [active,setActive]=useState(-1),[loading,setLoading]=useState(true),[error,setError]=useState("");
 const [position,setPosition]=useState({left:0,top:0,width:0,height:300}),[reload,setReload]=useState(0);
 const input=useRef<HTMLInputElement>(null),popup=useRef<HTMLDivElement>(null),listId=useId();
 useEffect(()=>{let alive=true;void apiRequest<{nodes:Course[]}>("/knowledge/curriculum").then(data=>{if(alive){setCourses(data.nodes.filter(n=>n.type==="Course").sort((a,b)=>Number(b.study_role==="focus")-Number(a.study_role==="focus")||String(a.metadata.course_code??a.title).localeCompare(String(b.metadata.course_code??b.title),"vi",{numeric:true})));setError("");}}).catch(e=>{if(alive)setError(errorMessage(e));}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;};},[reload]);
 const matches=courses.filter(c=>normalize(c.title+" "+(c.metadata.course_code??"")).includes(normalize(query.trim())));
 const show=()=>{if(!disabled){setOpen(true);setQuery("");setActive(-1);}};
 const choose=(course:Course)=>{onChange(course.title);setOpen(false);setActive(-1);input.current?.focus();};
 useEffect(()=>{if(!open)return;
  const place=()=>{const r=input.current?.getBoundingClientRect();if(r)setPosition({left:Math.max(8,r.left),top:r.bottom+6,width:Math.min(r.width,window.innerWidth-16),height:Math.max(130,Math.min(340,window.innerHeight-r.bottom-20))});};
  const outside=(e:PointerEvent)=>{if(!input.current?.contains(e.target as Node)&&!popup.current?.contains(e.target as Node))setOpen(false);};
  place();window.addEventListener("resize",place);window.addEventListener("scroll",place,true);document.addEventListener("pointerdown",outside);
  return()=>{window.removeEventListener("resize",place);window.removeEventListener("scroll",place,true);document.removeEventListener("pointerdown",outside);};
 },[open]);
 useEffect(()=>{if(active>=0)document.getElementById(`${listId}-${active}`)?.scrollIntoView({block:"nearest"});},[active,listId]);
 return <div className="course-autocomplete"><label htmlFor={id}>Học phần</label><input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open&&!disabled} aria-controls={open?listId:undefined} aria-activedescendant={open&&active>=0?`${listId}-${active}`:undefined} autoComplete="off" value={value} maxLength={255} disabled={disabled} placeholder="Chọn học phần hoặc gõ tên, mã môn…" onFocus={show} onClick={show} onBlur={()=>setOpen(false)} onChange={e=>{onChange(e.target.value);setQuery(e.target.value);setActive(-1);setOpen(true);}} onKeyDown={e=>{
   if(e.key==="Escape"||e.key==="Tab"){setOpen(false);return;}
   if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();setOpen(true);setActive(current=>Math.max(0,Math.min(matches.length-1,current+(e.key==="ArrowDown"?1:-1))));}
   if(e.key==="Enter"&&open){e.preventDefault();if(active>=0&&matches[active])choose(matches[active]);else setOpen(false);}
  }}/>{open&&!disabled&&createPortal(<div ref={popup} className="course-suggestions" style={{left:position.left,top:position.top,width:position.width,maxHeight:position.height}} onMouseDown={e=>e.preventDefault()}><div id={listId} role="listbox" aria-label="Học phần trong chương trình">{matches.map((course,index)=><div key={course.id} id={`${listId}-${index}`} role="option" aria-selected={index===active} className="course-suggestion" onMouseEnter={()=>setActive(index)} onClick={()=>choose(course)}><span>{course.title}</span><small>{course.metadata.course_code}{course.study_role==="focus"?" · Chuyên ngành":" · Nền tảng đã học"}</small></div>)}</div>{loading&&<p role="status">Đang tải học phần…</p>}{error&&<div role="alert"><p>{error}</p><button type="button" className="text-button" onClick={()=>{setLoading(true);setReload(n=>n+1);}}>Tải lại học phần</button></div>}{!loading&&!error&&!matches.length&&<p>Không có học phần phù hợp. Bạn có thể giữ tên vừa nhập.</p>}{!loading&&!error&&!!matches.length&&<p className="course-suggestion-hint">Gõ có hoặc không dấu để lọc · ↑ ↓ để chọn · Enter để xác nhận</p>}</div>,document.body)}</div>;
}
