import { useEffect, useState } from "react";
import { Actor, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";

export function ActorsPage() {
  const { token } = useAuth();
  const [actors, setActors] = useState<Actor[]>([]);

  useEffect(() => {
    if (!token) return;
    void apiClient.getActors(token).then(setActors);
  }, [token]);

  return (
    <section>
      <h2>演员管理</h2>
      <button className="button" type="button">新增演员</button>
      <ul>{actors.map((actor) => <li key={actor.id}>{actor.display_name}</li>)}</ul>
    </section>
  );
}
