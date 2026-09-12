import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { NextResponse } from "next/server";
import { validateReportForm } from "@/src/domain/intake";
import { createIncident } from "@/src/db/store";

export const runtime="nodejs";
export async function POST(request:Request){try{const form=await request.formData();const {report,image}=validateReportForm(form);const key=request.headers.get("Idempotency-Key")?.trim()||randomUUID();const id=randomUUID();const dir=process.env.FADS_UPLOAD_DIR??join(process.cwd(),"uploads");await mkdir(dir,{recursive:true});const ext=image.name.split(".").at(-1)?.replace(/[^a-z0-9]/gi,"")||"jpg";const path=join(dir,`${id}.${ext}`);await writeFile(path,Buffer.from(await image.arrayBuffer()));const accepted=createIncident(report,path,key);return NextResponse.json(accepted,{status:202});}catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Invalid report."},{status:400});}}
