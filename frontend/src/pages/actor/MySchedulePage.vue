<template>
     <section style="max-width: 1000px; margin: 0 auto;">
       <PageHeader title="我的排班" description="查看已发布班次和管理员允许展示的草稿班次。" />

       <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
         {{ error }}
       </div>

       <div class="panel" style="margin: 0;">
         <h3>排班排期列表 ({{ scheduleList.length }})</h3>
         <p v-if="scheduleList.length === 0" style="color: var(--text-secondary); margin-top: 10px;">暂无排班记录。</p>
         
         <div v-else style="overflow-x: auto; margin-top: 16px;">
           <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
             <thead>
               <tr style="border-bottom: 1px solid var(--panel-border); color: var(--text-secondary);">
                 <th style="padding: 12px;">日期</th>
                 <th style="padding: 12px;">场次</th>
                 <th style="padding: 12px;">角色</th>
                 <th style="padding: 12px;">发布状态</th>
               </tr>
             </thead>
             <tbody>
               <tr v-for="(item, idx) in scheduleList" :key="idx" style="border-bottom: 1px solid var(--panel-border);">
                 <td style="padding: 12px; font-weight: 500; color: #fff;">{{ item.date }}</td>
                 <td style="padding: 12px;">
                   <span class="badge badge-success">
                     {{ item.slot === "early" ? "下午场" : item.slot === "late" ? "晚场" : item.slot }}
                   </span>
                 </td>
                 <td style="padding: 12px; font-weight: 600; color: var(--primary);">{{ item.role }}</td>
                 <td style="padding: 12px;">
                   <span
                     :style="{
                       fontSize: '12px',
                       fontWeight: 600,
                       color: item.status === 'published' ? '#10b981' : '#f59e0b'
                     }"
                   >
                     {{ item.status === "published" ? "已发布" : "草稿" }}
                   </span>
                 </td>
               </tr>
             </tbody>
           </table>
         </div>
       </div>
     </section>
   </template>

   <script setup lang="ts">
   import { ref, onMounted } from "vue";
   import { useAuthStore } from "../../auth/store";
   import { actorApi } from "../../api/admin";
   import PageHeader from "../../components/PageHeader.vue";

   const authStore = useAuthStore();
   const scheduleList = ref<any[]>([]);
   const error = ref<string | null>(null);

   onMounted(async () => {
     if (!authStore.token) return;
     try {
       scheduleList.value = await actorApi.getSchedule(authStore.token);
     } catch (err: any) {
       error.value = err.message || "获取排班失败";
     }
   });
   </script>
