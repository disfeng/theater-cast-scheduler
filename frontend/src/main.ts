import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/dist/index.css";
import "./styles/tokens.css";
import "./styles/base.css";
import App from "./App.vue";
import { router } from "./router";
import { useAuthStore } from "./auth/store";
import { apiClient } from "./api/client";

const pinia = createPinia();
const app = createApp(App);

app.use(pinia).use(router).use(ElementPlus, { locale: zhCn });

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
