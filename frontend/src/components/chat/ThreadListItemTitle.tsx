import React from "react";
import { useAssistantState } from "@assistant-ui/react";

export const ThreadListItemTitle: React.FC<{ getThreadName: (id: string) => string }> = ({
  getThreadName,
}) => {
  const threadId = useAssistantState(({ threadListItem }) => threadListItem.id);
  const name = getThreadName(threadId);
  return <span className="font-medium">{name || "Untitled conversation"}</span>;
};
