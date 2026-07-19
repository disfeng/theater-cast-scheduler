import type { EntitlementItem, EntitlementItemType, PlayerInventorySummary } from "./types";

export type InventoryGroupMode = "month" | "type";
export type InventoryGroup = { key: string; label: string; items: EntitlementItem[] };

export function filterAndSortPlayers(rows: PlayerInventorySummary[], query: string) {
  const keyword=query.trim().toLocaleLowerCase();
  return rows
    .filter(row=>!keyword||row.display_name.toLocaleLowerCase().includes(keyword)||row.normalized_name.toLocaleLowerCase().includes(keyword)||row.sort_key.includes(keyword))
    .slice()
    .sort((a,b)=>a.sort_key.localeCompare(b.sort_key)||a.normalized_name.localeCompare(b.normalized_name)||a.player_id-b.player_id);
}

const monthLabel=(key:string)=>{const [year,month]=key.split("-");return `${year}年${Number(month)}月`};

export function groupInventoryItems(items: EntitlementItem[], definitions: EntitlementItemType[], mode: InventoryGroupMode):InventoryGroup[] {
  const definitionMap=new Map(definitions.map(item=>[item.id,item]));
  const groups=new Map<string,EntitlementItem[]>();
  for(const item of items){const key=mode==="month"?(item.source_month?.slice(0,7)||item.granted_at.slice(0,7)):String(item.item_type_id);groups.set(key,[...(groups.get(key)||[]),item])}
  return [...groups].map(([key,groupItems])=>({key,label:mode==="month"?monthLabel(key):(definitionMap.get(Number(key))?.display_name??`类型 #${key}`),items:groupItems.slice().sort((a,b)=>a.expires_at.localeCompare(b.expires_at)||a.id-b.id)})).sort((a,b)=>mode==="month"?b.key.localeCompare(a.key):(definitionMap.get(Number(a.key))?.sort_order??9999)-(definitionMap.get(Number(b.key))?.sort_order??9999)||a.label.localeCompare(b.label));
}
