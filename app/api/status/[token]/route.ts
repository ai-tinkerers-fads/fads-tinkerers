import { NextResponse } from "next/server";
import { incidentByToken, safeStatus } from "@/src/db/store";
export const runtime="nodejs";export const dynamic="force-dynamic";
export async function GET(_:Request,{params}:{params:Promise<{token:string}>}){const {token}=await params;const incident=incidentByToken(token);if(!incident)return NextResponse.json({error:"Not found"},{status:404});return NextResponse.json(safeStatus(incident));}
