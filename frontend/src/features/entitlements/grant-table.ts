import type { EntitlementItemType, PlayerProfile } from "./types";

export function parsePastedPlayerNames(text: string): string[] {
  const seen=new Set<string>();
  return text.split(/\r?\n/).map(value=>value.trim()).filter(value=>{const key=value.toLocaleLowerCase();if(!value||seen.has(key))return false;seen.add(key);return true});
}

export type GrantPlayerRow = { rawName: string; playerId: number | null; playerName: string; status: "matched" | "pending" | "ambiguous"; candidates: PlayerProfile[]; quantities: Record<number, number> };

export function createGrantRow(rawName:string, definitions:EntitlementItemType[]):GrantPlayerRow {
  return {rawName,playerId:null,playerName:rawName,status:"pending",candidates:[],quantities:Object.fromEntries(definitions.map(item=>[item.id,0]))};
}

export type GrantPlayerMatch = { raw_name: string; player: PlayerProfile | null; candidates: PlayerProfile[]; created: boolean };

export function applyGrantPlayerMatch(row: GrantPlayerRow, result: GrantPlayerMatch) {
  row.candidates = result.candidates;
  if (result.player) {
    row.playerId = result.player.id;
    row.playerName = result.player.display_name;
    row.status = result.player.status === "active" ? "matched" : "pending";
    return;
  }
  row.playerId = null;
  row.playerName = result.raw_name;
  row.status = result.candidates.length > 1 ? "ambiguous" : "pending";
}

export const grantRowIsResolved = (row: GrantPlayerRow) => row.status === "matched" && row.playerId !== null;

export function expandGrantItems(rows:GrantPlayerRow[], sourceMonth:string|null, sourceLabel:string, expiresAt:string|null, boundActorId:number|null=null) {
  return rows.flatMap(row=>Object.entries(row.quantities).flatMap(([typeId,quantity])=>Array.from({length:Number(quantity)||0},()=>({player_id:row.playerId!,item_type_id:Number(typeId),quantity:1,source_month:sourceMonth,source_label:sourceLabel,expires_at:expiresAt,notes:null,bound_actor_id:boundActorId}))));
}
