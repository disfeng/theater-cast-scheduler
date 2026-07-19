import { fireEvent, screen, waitFor, within } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { renderAdminRoute } from "./helpers/render-app";
import { entitlementLabel, formatEntitlementDate, toIsoEndOfDay } from "../src/features/entitlements/format";
import { applyGrantPlayerMatch, createGrantRow, expandGrantItems, grantRowIsResolved, parsePastedPlayerNames } from "../src/features/entitlements/grant-table";
import { summarizeCardResults } from "../src/features/entitlements/top-three-grants";
import mainSource from "../src/main.ts?raw";
import grantBatchSource from "../src/components/admin/GrantBatchTab.vue?raw";
const baseStyles=readFileSync(`${process.cwd()}/src/styles/base.css`,"utf8");

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

test("发放玩家匹配结果统一映射为行状态",()=>{
  const row=createGrantRow("小雨",[]);
  const candidate={id:8,display_name:"小雨A",normalized_name:"小雨a",status:"active"} as const;
  applyGrantPlayerMatch(row,{raw_name:"小雨",player:null,candidates:[candidate,{...candidate,id:9,display_name:"小雨B"}],created:false});
  expect(row.status).toBe("ambiguous");expect(row.candidates).toHaveLength(2);expect(grantRowIsResolved(row)).toBe(false);
  applyGrantPlayerMatch(row,{raw_name:"小雨",player:candidate,candidates:[],created:false});
  expect(row.status).toBe("matched");expect(row.playerId).toBe(8);expect(grantRowIsResolved(row)).toBe(true);
});

test("榜三批量结果区分成功跳过与失败 Card",()=>{
  expect(summarizeCardResults([
    {actorId:1,actorName:"小A",outcome:"granted"},
    {actorId:2,actorName:"小银",outcome:"skipped",reason:"存在待确认玩家"},
    {actorId:3,actorName:"小奇",outcome:"failed",reason:"网络错误"},
  ])).toEqual({successful:["小A"],skipped:["小银（存在待确认玩家）"],failed:["小奇（网络错误）"]});
});

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
  await fireEvent.click(screen.getByRole("combobox",{name:"榜单演员"}));
  const actorOption=await screen.findByRole("option",{name:"小A"});
  await fireEvent.click(actorOption);
  await waitFor(()=>expect(actorOption).toHaveAttribute("aria-selected","true"));
  expect(await screen.findByRole("columnheader",{name:"榜三指定"})).toBeInTheDocument();
  expect(screen.queryByRole("columnheader",{name:"万能指定"})).not.toBeInTheDocument();
});

test("全局原生表单样式不覆盖 Element Plus 内部输入框",()=>{
  expect(baseStyles).toContain('input:not([class^="el-"])');
  expect(baseStyles).not.toContain('input:not(.el-input__inner)');
});

test("发放页可行内确认临时玩家",async()=>{
  const requests:{path:string;method:string;body:any}[]=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input).replace(/https?:\/\/localhost:\d+/,"");
    const method=init?.method||"GET";
    const body=init?.body?JSON.parse(String(init.body)):null;
    requests.push({path,method,body});
    if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([{id:1,theater_id:2,code:"universal",display_name:"万能指定",category:"designation",designation_type:"universal",priority:300,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0}]);
    if(path==="/admin/theaters/2/entitlement-grant-batches")return Response.json([]);
    if(path==="/admin/actors"||path.startsWith("/admin/roles?"))return Response.json([]);
    if(path==="/admin/theaters/2/entitlement-grant-player-matches")return Response.json([{raw_name:"新玩家",player:{id:7,display_name:"新玩家",normalized_name:"新玩家",status:"provisional"},candidates:[],created:true}]);
    if(path==="/admin/player-profiles/7"&&method==="PATCH")return Response.json({id:7,display_name:"新玩家",normalized_name:"新玩家",status:"active"});
    return Response.json({detail:`unexpected:${method}:${path}`},{status:500});
  }));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=grants");
  await fireEvent.click(await screen.findByRole("button",{name:"批量粘贴玩家"}));
  await fireEvent.update(screen.getByPlaceholderText(/每行一个玩家昵称/),"新玩家");
  await fireEvent.click(screen.getByRole("button",{name:"匹配并添加"}));
  expect(await screen.findByText("待确认")).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button",{name:"确认玩家"}));
  await fireEvent.click(await screen.findByRole("button",{name:"确认玩家身份"}));
  await waitFor(()=>expect(screen.getByText("已匹配")).toBeInTheDocument());
  expect(requests).toContainEqual({path:"/admin/player-profiles/7",method:"PATCH",body:{status:"active"}});
});

test("发放页可从重名候选中选择已有正式玩家",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input).replace(/https?:\/\/localhost:\d+/,"");
    if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([{id:1,theater_id:2,code:"universal",display_name:"万能指定",category:"designation",designation_type:"universal",priority:300,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0}]);
    if(path==="/admin/theaters/2/entitlement-grant-batches")return Response.json([]);
    if(path==="/admin/actors"||path.startsWith("/admin/roles?"))return Response.json([]);
    if(path==="/admin/theaters/2/entitlement-grant-player-matches")return Response.json([{raw_name:"小雨",player:null,candidates:[{id:8,display_name:"小雨（微信A）",normalized_name:"小雨a",status:"active"},{id:9,display_name:"小雨（微信B）",normalized_name:"小雨b",status:"active"}],created:false}]);
    return Response.json({detail:`unexpected:${path}`},{status:500});
  }));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=grants");
  await fireEvent.click(await screen.findByRole("button",{name:"批量粘贴玩家"}));
  await fireEvent.update(screen.getByPlaceholderText(/每行一个玩家昵称/),"小雨");
  await fireEvent.click(screen.getByRole("button",{name:"匹配并添加"}));
  const candidateSelect=await screen.findByRole("combobox",{name:"选择小雨对应玩家"});
  await fireEvent.click(candidateSelect);
  await fireEvent.click(await screen.findByRole("option",{name:"小雨（微信A）"}));
  await waitFor(()=>expect(screen.getByText("已匹配")).toBeInTheDocument());
});

test("发放玩家列使用紧凑固定宽度",()=>{
  expect(grantBatchSource).toContain('width="300"');
  expect(grantBatchSource).not.toContain('label="玩家" fixed min-width="190"');
});

test("榜三工作台可选择全部演员并分别粘贴玩家",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input).replace(/https?:\/\/localhost:\d+/,"");
    if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([{id:2,theater_id:2,code:"top-three",display_name:"榜三指定",category:"designation",designation_type:"top_three",priority:200,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:1}]);
    if(path==="/admin/theaters/2/entitlement-grant-batches")return Response.json([]);
    if(path==="/admin/actors")return Response.json([{id:8,display_name:"小A",role_ids:[21],rating_level:"normal",max_consecutive_performances:3,low_rating_monthly_cap:null,notes:null},{id:9,display_name:"小银",role_ids:[21],rating_level:"normal",max_consecutive_performances:3,low_rating_monthly_cap:null,notes:null}]);
    if(path.startsWith("/admin/roles?"))return Response.json([{id:21,theater_id:2,name:"林月棠",group_name:"女",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-grant-player-matches")return Response.json([{raw_name:"玩家甲",player:{id:17,display_name:"玩家甲",normalized_name:"玩家甲",status:"active"},candidates:[],created:false}]);
    return Response.json({detail:`unexpected:${path}`},{status:500});
  }));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=grants");
  await fireEvent.click(await screen.findByRole("radio",{name:"榜三指定发放"}));
  await fireEvent.click(await screen.findByRole("button",{name:"选择全部演员"}));
  const cards=await screen.findAllByTestId("top-three-actor-card");
  expect(cards).toHaveLength(2);expect(screen.getByText("榜三指定 · 小A")).toBeInTheDocument();expect(screen.getByText("榜三指定 · 小银")).toBeInTheDocument();
  await fireEvent.click(within(cards[0]).getByRole("button",{name:"为小A粘贴玩家"}));
  await fireEvent.update(screen.getByPlaceholderText(/每行一个玩家昵称/),"玩家甲");
  await fireEvent.click(screen.getByRole("button",{name:"匹配并添加"}));
  await waitFor(()=>expect(within(cards[0]).getByText("玩家甲")).toBeInTheDocument());
  expect(within(cards[1]).queryByText("玩家甲")).not.toBeInTheDocument();
  expect(within(cards[0]).getByRole("spinbutton")).toHaveValue(1);
});

test("道具运营卡只展示名称不显示内部编码",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{const path=String(input).replace(/https?:\/\/localhost:\d+/,"");if(path==="/admin/theaters")return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);if(path==="/admin/theaters/2/entitlement-item-types")return Response.json([{id:3,theater_id:2,code:"universal_designation",display_name:"万能指定",category:"designation",designation_type:"universal",priority:300,default_validity_days:90,color:"#409eff",icon:null,description:null,is_active:true,sort_order:0}]);if(["/admin/actors","/admin/roles"].includes(path))return Response.json([]);return Response.json({detail:`unexpected:${path}`},{status:500})}));
  await renderAdminRoute("/admin/entitlements?theater_id=2&tab=catalog");
  expect((await screen.findAllByText("万能指定")).length).toBeGreaterThan(0);
  expect(screen.queryByText("universal_designation")).not.toBeInTheDocument();
});
