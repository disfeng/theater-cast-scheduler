import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import "./styles/tokens.css";
import "./styles/base.css";
import App from "./App.vue";
import { router } from "./router";
import { useAuthStore } from "./auth/store";
import { apiClient } from "./api/client";

const pinia = createPinia();
const app = createApp(App);

app.use(pinia).use(router).use(ElementPlus);

apiClient.setAuthErrorHandler((status) => {
  const auth = useAuthStore(pinia);
  if (status === 401) {
    auth.logout();
    void router.replace({ path: "/login", query: { redirect: router.currentRoute.value.fullPath } });
    return;
  }
  void router.replace(auth.role === "actor" ? "/actor/schedule" : "/admin/dashboard");
});

app.mount("#app");
