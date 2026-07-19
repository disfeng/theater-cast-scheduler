import { fireEvent, screen, waitFor } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";

beforeEach(() => {
  localStorage.clear(); vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path=String(input).replace(/https?:\/\/localhost:\d+/,"");
    if(path==="/admin/theaters") return Response.json([{id:2,name:"西安幽州剧场",is_active:true}]);
    if(path==="/admin/theaters/2/entitlement-item-types") return Response.json([]);
    if(path==="/admin/theaters/2/entitlement-ledger") return Response.json({records:[],next_cursor:null});
    if(["/admin/actors","/admin/roles"].includes(path)) return Response.json([]);
    return Response.json({detail:`unexpected:${path}`},{status:500});
  }));
});

test("权益管理使用剧场上下文和四个业务页签", async()=>{
  const view=await renderAdminRoute("/admin/entitlements?theater_id=2&tab=catalog");
  expect(await screen.findByRole("heading",{name:"权益管理"})).toBeInTheDocument();
  for(const name of ["道具配置","权益发放","权益背包","权益流水"]) expect(screen.getByRole("tab",{name})).toBeInTheDocument();
  expect(screen.getByRole("combobox",{name:"当前剧场"})).toBeInTheDocument();
  expect(view.container.querySelector(".theater-context--compact")).toBeInTheDocument();
});

test("剧场和页签通过查询参数恢复", async()=>{
  const view=await renderAdminRoute("/admin/entitlements?theater_id=2&tab=inventory");
  expect(await screen.findByRole("tab",{name:"权益背包"})).toHaveAttribute("aria-selected","true");
  expect(view.container.querySelector(".inventory-search-bar")).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("tab",{name:"权益流水"}));
  await waitFor(()=>expect(view.router.currentRoute.value.query).toMatchObject({theater_id:"2",tab:"ledger"}));
});
