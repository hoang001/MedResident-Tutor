import type {CSSProperties} from "react";
const paths={
  home:"m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  book:"M12 5C9 3 5 3 2 4v16c3-1 7-1 10 1m0-16c3-2 7-2 10-1v16c-3-1-7-1-10 1Zm0 0v16",
  practice:"M8 4H5v17h14V4h-3M9 2h6v5H9Zm-1 9h8m-8 4h5",
  history:"M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2",
  chart:"M4 3v18h17M8 16v-4m5 4V8m5 8V5",
  files:"M14 2H5v20h14V7Zm0 0v6h5M8 12h8m-8 4h8",
  edit:"m15 4 5 5M4 20l5-1L21 7l-5-5L4 14Zm0 0h16",
  person:"M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2",
  logout:"M10 4H4v16h6m5-12 4 4-4 4m-6-4h10",arrow:"M4 12h16m-6-6 6 6-6 6",
  menu:"M3 6h18M3 12h18M3 18h18",close:"m6 6 12 12M18 6 6 18",
  search:"M20 20l-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z",check:"m5 12 4 4L19 6",
  info:"M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",alert:"m12 3 10 18H2Zm0 6v5m0 3v.1",
  clock:"M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  source:"M10 13a5 5 0 0 0 7 0l4-4a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-4 4a5 5 0 0 0 7 7l2-2",
  chevron:"m8 4 8 8-8 8",down:"m6 9 6 6 6-6",save:"M19 21H5a2 2 0 0 1-2-2V3h15l3 3v13a2 2 0 0 1-2 2ZM7 3v6h10V3M7 21v-8h10v8",
} as const;
export type IconName=keyof typeof paths;
export function Icon({name,size=20,className,style}:{name:IconName;size?:number;className?:string;style?:CSSProperties}) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} style={style}><path d={paths[name]}/></svg>;
}
