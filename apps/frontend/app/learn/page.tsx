"use client";
import {Suspense} from "react";
import {useSearchParams} from "next/navigation";
import {useWorkspace} from "@/lib/knowledge";
import {ExerciseCatalog} from "@/components/ExerciseCatalog";
import {PracticeWorkspace} from "@/components/PracticeWorkspace";
import {Alert,Loading} from "@/components/ui";
function Learn(){
 const {user,error}=useWorkspace();const params=useSearchParams();
 const question=params.get("question")??undefined;const attempt=params.get("attempt")??undefined;
 if(!user)return <main className="container">{error?<Alert kind="error">{error}</Alert>:<Loading/>}</main>;
 return question||attempt?<PracticeWorkspace key={attempt??question} userId={user.id} questionId={question} attemptId={attempt}/>:<ExerciseCatalog userId={user.id} initialTopic={params.get("topic")??""}/>;
}
export default function LearnPage(){return <Suspense fallback={<main className="container"><Loading/></main>}><Learn/></Suspense>;}
