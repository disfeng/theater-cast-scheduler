import type { EntitlementItemType } from "./types";

export function parsePastedPlayerNames(text: string): string[] {
  const seen=new Set<string>();
  return text.split(/\r?\n/).map(value=>value.trim()).filter(value=>{const key=value.toLocaleLowerCase();if(!value||seen.has(key))return false;seen.add(key);return true});
}

export type GrantPlayerRow = { rawName: string; playerId: number | null; playerName: string; status: "matched" | "pending" | "ambiguous"; quantities: Record<number, number> };

export function createGrantRow(rawName:string, definitions:EntitlementItemType[]):GrantPlayerRow {
  return {rawName,playerId:null,playerName:rawName,status:"pending",quantities:Object.fromEntries(definitions.map(item=>[item.id,0]))};
}

export function expandGrantItems(rows:GrantPlayerRow[], sourceMonth:string|null, sourceLabel:string, expiresAt:string|null) {
  return rows.flatMap(row=>Object.entries(row.quantities).flatMap(([typeId,quantity])=>Array.from({length:Number(quantity)||0},()=>({player_id:row.playerId!,item_type_id:Number(typeId),quantity:1,source_month:sourceMonth,source_label:sourceLabel,expires_at:expiresAt,notes:null}))));
}
