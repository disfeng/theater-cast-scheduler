import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import PageHeader from "../src/components/PageHeader.vue";

describe("PageHeader", () => {
  it("uses the shared compact vertical rhythm", () => {
    const wrapper = mount(PageHeader, {
      props: { title: "指定与权益", description: "页面说明" },
    });

    expect(wrapper.get(".page-header").attributes("style")).toContain("margin-bottom: 20px");
    expect(wrapper.get(".page-header__copy").attributes("style")).toContain("gap: 8px");
    expect(wrapper.get("h2").attributes("style")).toContain("margin: 0px");
    expect(wrapper.get("p").attributes("style")).toContain("margin: 0px");
  });
});
