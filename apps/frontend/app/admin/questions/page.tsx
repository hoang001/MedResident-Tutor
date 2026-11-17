"use client";
import {AdminOnly} from "@/components/AdminOnly";
import QuestionBankWorkspace from "@/components/QuestionBankWorkspace";
export default function QuestionsPage(){return <AdminOnly><QuestionBankWorkspace/></AdminOnly>;}
