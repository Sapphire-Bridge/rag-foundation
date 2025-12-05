import React from "react";
import { useAssistantApi } from "@assistant-ui/react";

export const ThreadEventsReset: React.FC<{ onReset: () => void }> = ({ onReset }) => {
  const api = useAssistantApi();
  React.useEffect(() => {
    return api.on("thread-list-item.switched-to", () => onReset());
  }, [api, onReset]);
  return null;
};
