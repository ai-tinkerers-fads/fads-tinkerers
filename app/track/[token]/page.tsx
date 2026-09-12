import Link from "next/link";
import { notFound } from "next/navigation";
import { incidentByToken, safeStatus } from "@/src/db/store";

export const dynamic="force-dynamic";
const stages=["received","under_review","crew_proposed","scheduled","work_underway","resolved"];
export default async function TrackingPage({params}:{params:Promise<{token:string}>}){
  const {token}=await params;const incident=incidentByToken(token);if(!incident)notFound();const status=safeStatus(incident);const active=Math.max(0,stages.indexOf(status.milestone));
  return <main><header className="masthead"><Link className="brand" href="/"><span>FADS</span> Road Response</Link><span>Report {status.incidentId}</span></header><section className="status-page"><p className="eyebrow" style={{color:"#174f37"}}>Live road report</p><h1>{status.issueLabel} at {status.address}</h1><div className="status-card"><div className="status-line"><div><p>Current status</p><h2>{status.progressMessage}</h2></div><span className="pill">{status.milestone.replaceAll("_"," ")}</span></div><div className="timeline" aria-label="Progress">{stages.map((stage,index)=><span key={stage} className={index<=active?"active":""}/>)}</div>{status.queuePosition&&<p>Queue position: <strong>{status.queuePosition}</strong></p>}{status.estimatedResolutionAt&&<p>Expected completion: <strong>{new Date(status.estimatedResolutionAt).toLocaleString()}</strong></p>}{status.fallbackUsed&&<p className="privacy">Demo fallback used during evidence analysis; dispatcher review required.</p>}<p className="privacy">Last updated {new Date(status.updatedAt).toLocaleString()}</p></div></section></main>;
}
