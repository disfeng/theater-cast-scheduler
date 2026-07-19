import { fireEvent, screen, waitFor } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";
import { entitlementLabel, formatEntitlementDate, toIsoEndOfDay } from "../src/features/entitlements/format";
import { createGrantRow, expandGrantItems, parsePastedPlayerNames } from "../src/features/entitlements/grant-table";
import mainSource from "../src/main.ts?raw";
import grantBatchSource from "../src/components/admin/GrantBatchTab.vue?raw";

beforeEach(()=>{localStorage.clear();vi.restoreAllMocks()});

test("空道具目录可创建默认指定道具",async()=>{
  const requests:string[]=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const path=String(input).replace(/https?:\/\/localhost:\d+/,"");if((init?.method||"GET")!=="GET")requests.push(path);if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([]);if(path==="/admin/theaters/2/entitlement-item-types/default-designations")return Response.json([]);if(["/admin/actors","/admin/roles"].includes(path))return Response.json([]);return Response.json({detail:`unexpected:${path}`},{status:500})}));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=catalog");
  await fireEvent.click(await screen.findByRole("button",{name:"创建万能、榜三和对位指定"}));
  expect(await screen.findByRole("dialog",{name:"创建默认指定道具"})).toBeInTheDocument();
  expect(screen.getByText("万能指定")).toBeInTheDocument();
  expect(screen.getByText("榜三指定")).toBeInTheDocument();
  expect(screen.getByText("对位指定")).toBeInTheDocument();
  expect(screen.getByText("已存在的默认道具不会重复创建")).toBeInTheDocument();
  await fireEvent.click(await screen.findByRole("button",{name:"确认创建"}));
  await waitFor(()=>expect(requests).toContain("/admin/theaters/2/entitlement-item-types/default-designations"));
});

test("权益流水读取当前剧场并显示道具事件",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{const path=String(input).replace(/https?:\/\/localhost:\d+/,"");if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([]);if(path==="/admin/theaters/2/entitlement-ledger")return Response.json({records:[{id:1,item_id:9,serial_number:"XA-0001",player_id:7,player_name:"兹",item_type_id:3,item_type_name:"榜三指定",bound_actor_id:8,bound_actor_name:"小A",event_type:"granted",occurred_at:"2026-07-19T10:00:00",from_status:null,to_status:"available",purpose:null,reason:"月榜发放",note:null,performance_id:null,designation_id:null}],next_cursor:null});if(["/admin/actors","/admin/roles"].includes(path))return Response.json([]);return Response.json({detail:`unexpected:${path}`},{status:500})}));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=ledger");
  expect(await screen.findByText("XA-0001")).toBeInTheDocument();expect(screen.getByText("兹")).toBeInTheDocument();expect(screen.getByText("榜三指定 · 小A")).toBeInTheDocument();expect(screen.getAllByText("已发放").length).toBeGreaterThan(0);
});

test("业务日期和权益状态保持中文",()=>{const iso=toIsoEndOfDay("2026-07-01")!;expect(formatEntitlementDate(iso)).toBe("2026年7月1日");expect(entitlementLabel("manually_consumed")).toBe("手工核销")});

test("Element Plus 全局使用中文且来源月份保留稳定提交格式",()=>{
  expect(mainSource).toContain('element-plus/es/locale/lang/zh-cn');
  expect(mainSource).toContain('ElementPlus, { locale: zhCn }');
  expect(grantBatchSource).toContain('format="YYYY年M月"');
  expect(grantBatchSource).toContain('value-format="YYYY-MM"');
});

test("批量玩家去重并按动态道具数量展开实例",()=>{const definitions=[{id:3,theater_id:2,code:"drink",display_name:"饮品券",category:"general",designation_type:null,priority:0,default_validity_days:30,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0}] as any;expect(parsePastedPlayerNames(" 小A\nKiki\n小a \n")).toEqual(["小A","Kiki"]);const row=createGrantRow("小A",definitions);row.playerId=7;row.status="matched";row.quantities[3]=2;expect(expandGrantItems([row],"2026-07-01","七月活动",null)).toHaveLength(2)});

test("权益发放区分通用批量与绑定演员的榜三模式",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input).replace(/https?:\/\/localhost:\d+/,"");
    if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([
      {id:1,theater_id:2,code:"universal",display_name:"万能指定",category:"designation",designation_type:"universal",priority:300,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0},
      {id:2,theater_id:2,code:"top-three",display_name:"榜三指定",category:"designation",designation_type:"top_three",priority:200,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:1},
    ]);
    if(path==="/admin/theaters/2/entitlement-grant-batches")return Response.json([]);
    if(path==="/admin/actors")return Response.json([{id:8,display_name:"小A",role_ids:[21],rating_level:"normal",max_consecutive_performances:3,low_rating_monthly_cap:null,notes:null}]);
    if(path.startsWith("/admin/roles?"))return Response.json([{id:21,theater_id:2,name:"林月棠",group_name:"女",is_active:true}]);
    return Response.json({detail:`unexpected:${path}`},{status:500});
  }));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=grants");
  expect(await screen.findByRole("radio",{name:"通用批量发放"})).toBeChecked();
  expect(screen.queryByRole("combobox",{name:"榜单演员"})).not.toBeInTheDocument();
  await fireEvent.click(screen.getByRole("radio",{name:"榜三指定发放"}));
  expect(await screen.findByRole("combobox",{name:"榜单演员"})).toBeInTheDocument();
  expect(screen.getByRole("columnheader",{name:"榜三指定"})).toBeInTheDocument();
  expect(screen.queryByRole("columnheader",{name:"万能指定"})).not.toBeInTheDocument();
});

test("道具运营卡只展示名称不显示内部编码",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{const path=String(input).replace(/https?:\/\/localhost:\d+/,"");if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([{id:3,theater_id:2,code:"universal_designation",display_name:"万能指定",category:"designation",designation_type:"universal",priority:300,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0}]);if(["/admin/actors","/admin/roles"].includes(path))return Response.json([]);return Response.json({detail:`unexpected:${path}`},{status:500})}));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=catalog");
  expect((await screen.findAllByText("万能指定")).length).toBeGreaterThan(0);
  expect(screen.queryByText("universal_designation")).not.toBeInTheDocument();
});
