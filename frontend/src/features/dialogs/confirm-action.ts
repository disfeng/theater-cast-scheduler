import { ElMessageBox } from "element-plus";

export type ConfirmActionTone = "primary" | "warning" | "danger";

export interface ConfirmActionOptions {
  title: string;
  message: string;
  tone?: ConfirmActionTone;
  confirmButtonText?: string;
  cancelButtonText?: string;
  alert?: boolean;
}

const elementType = (tone: ConfirmActionTone) => tone === "danger" ? "error" : tone === "warning" ? "warning" : "info";

export async function confirmAction(options: ConfirmActionOptions): Promise<void> {
  const tone = options.tone ?? "primary";
  const messageBoxOptions = {
    type: elementType(tone),
    customClass: `app-message-box app-message-box--${tone}`,
    confirmButtonText: options.confirmButtonText ?? "确认",
    cancelButtonText: options.cancelButtonText ?? "取消",
    distinguishCancelAndClose: true,
  } as const;

  if (options.alert) {
    await ElMessageBox.alert(options.message, options.title, messageBoxOptions);
    return;
  }
  await ElMessageBox.confirm(options.message, options.title, messageBoxOptions);
}
