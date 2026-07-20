import Link from "next/link";

const links = [
  ["Dashboard", "/dashboard"],
  ["Learn", "/learn"],
  ["Exams", "/exams"],
  ["Progress", "/progress"],
  ["Documents", "/admin/documents"],
];

export function Nav() {
  return (
    <header className="nav">
      <Link className="brand" href="/">Resident Learning</Link>
      <nav>{links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}</nav>
    </header>
  );
}
