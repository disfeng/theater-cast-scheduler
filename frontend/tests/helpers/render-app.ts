import { render } from "@testing-library/vue";
import { createPinia, setActivePinia } from "pinia";
import ElementPlus from "element-plus";
import { router } from "../../src/router";
import App from "../../src/App.vue";

export async function renderApp(path: string) {
  const pinia = createPinia();
  setActivePinia(pinia);

  // Set router to target path before rendering
  router.push(path);
  await router.isReady();

  const result = render(App, {
    global: {
      plugins: [pinia, router, ElementPlus],
    },
  });

  return {
    ...result,
    router,
  };
}

export async function renderAdminRoute(path: string) {
  localStorage.setItem("token", "admin-token");
  localStorage.setItem("role", "admin");
  return renderApp(path);
}

export async function renderActorRoute(path: string) {
  localStorage.setItem("token", "actor-token");
  localStorage.setItem("role", "actor");
  return renderApp(path);
}

export async function loginAsAdmin() {
  return renderAdminRoute("/admin/dashboard");
}
