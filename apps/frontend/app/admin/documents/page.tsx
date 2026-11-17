"use client";
import {AdminOnly} from "@/components/AdminOnly";
import DocumentWorkspace from "@/components/DocumentWorkspace";
export default function DocumentsPage(){return <AdminOnly><DocumentWorkspace/></AdminOnly>;}
