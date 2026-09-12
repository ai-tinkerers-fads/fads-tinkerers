/* eslint-disable @next/next/no-img-element -- blob previews are local and cannot use Next image optimization */
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type WorkflowOption = { id: string; label: string; description: string };

export function ReportForm({ workflows }: { workflows: WorkflowOption[] }) {
  const router = useRouter();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [preview,setPreview]=useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form=new FormData(event.currentTarget);
    const key=crypto.randomUUID();
    const response=await fetch("/api/reports",{method:"POST",headers:{"Idempotency-Key":key},body:form});
    const body=await response.json() as {statusUrl?:string;error?:string};
    if(!response.ok||!body.statusUrl){setError(body.error??"Could not submit the report.");setBusy(false);return;}
    router.push(body.statusUrl);
  }

  function locate() {
    navigator.geolocation.getCurrentPosition((position)=>{
      const form=document.querySelector<HTMLFormElement>("#report-form");
      if(form){(form.elements.namedItem("latitude") as HTMLInputElement).value=String(position.coords.latitude);(form.elements.namedItem("longitude") as HTMLInputElement).value=String(position.coords.longitude);}
    },()=>setError("Location permission was not granted. Enter coordinates manually."));
  }

  return <form id="report-form" onSubmit={submit} className="report-form">
    <fieldset><legend>1. Choose the closest issue</legend><div className="issue-grid">{workflows.map((item)=><label className="issue-card" key={item.id}><input type="radio" name="issueType" value={item.id} required/><span><strong>{item.label}</strong><small>{item.description}</small></span></label>)}</div></fieldset>
    <fieldset><legend>2. Add evidence and location</legend><div className="evidence-grid"><label className="upload"><input type="file" name="image" accept="image/*" required onChange={(event)=>{const file=event.target.files?.[0];if(file)setPreview(URL.createObjectURL(file));}}/>{preview?<img src={preview} alt="Road damage preview"/>:<span><b>Upload road photo</b><small>JPG, PNG or WebP · max 10 MB</small></span>}</label><div className="fields"><label>Street address<input name="address" placeholder="Pine Street near 4th Avenue" required/></label><div className="split"><label>Latitude<input name="latitude" inputMode="decimal" required/></label><label>Longitude<input name="longitude" inputMode="decimal" required/></label></div><button type="button" className="secondary" onClick={locate}>Use my current location</button><label>Additional details <em>optional</em><textarea name="description" placeholder="Both lanes are blocked…" rows={3}/></label></div></div></fieldset>
    <fieldset><legend>3. How can dispatch reach you?</legend><div className="contact-grid"><label>Name<input name="residentName" required/></label><label>Email<input name="residentEmail" type="email" required/></label><label>Phone<input name="residentPhone" type="tel" required/></label></div><p className="privacy">Demo data is visible to this workspace. Use synthetic contact details only.</p></fieldset>
    {error&&<p className="error" role="alert">{error}</p>}<button className="submit" disabled={busy}>{busy?"Submitting report…":"Submit road report"}</button>
  </form>;
}
