"use client";

import { useState } from "react";
import { useSkills, useSelectSkills, useSkillCache } from "@/hooks/use-api";
import { Card, Badge, ProgressBar } from "@/components/ui/card";
import type { Skill, SkillSelection } from "@/types/hermes";
import { CenterHeader } from "@/components/center-scaffold";

export function SkillsCenter() {
  const { data: skills } = useSkills();
  const { data: cache } = useSkillCache();
  const [taskDesc, setTaskDesc] = useState("");
  const { data: selected } = useSelectSkills(taskDesc);

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Skills Center"
        subtitle="Distribution dynamique et sélection intelligente des compétences"
      />

      {/* Skill selection */}
      <Card title="Sélection automatique" subtitle="Décrivez une tâche pour obtenir des recommandations de compétences" className="mb-6">
        <input
          type="text"
          value={taskDesc}
          onChange={(e) => setTaskDesc(e.target.value)}
          placeholder='ex. « Construire une API REST avec authentification »'
          className="w-full bg-hermes-bg border border-hermes-border rounded-lg px-4 py-2.5 text-sm text-hermes-text font-mono focus:border-hermes-amber outline-none mb-3"
        />
        {selected && (
          <div className="flex flex-col gap-2">
            {selected.map((s) => (
              <SelectionRow key={s.skill_id} selection={s} />
            ))}
            {selected.length === 0 && (
              <p className="text-xs text-hermes-muted py-2">Aucune compétence correspondante. Essayez une description plus longue.</p>
            )}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-4">
        {/* Skills list */}
        <Card title="Compétences enregistrées" subtitle={`${skills?.length || 0} compétence(s)`}>
          <div className="flex flex-col gap-2 max-h-[400px] overflow-y-auto">
            {skills?.map((skill) => (
              <SkillCard key={skill.id} skill={skill} />
            ))}
          </div>
        </Card>

        {/* Cache */}
        <Card title="État du cache" subtitle={cache ? `${Object.keys(cache).length} entrée(s)` : "Chargement…"}>
          {cache && (
            <div className="flex flex-col gap-2">
              {Object.entries(cache).slice(0, 8).map(([key, val]: [string, any]) => (
                <div key={key} className="flex items-center justify-between p-2 bg-hermes-bg rounded text-xs">
                  <span className="text-hermes-text font-mono">{key}</span>
                  <Badge variant={val?.status === "active" ? "success" : "default"}>
                    {val?.status || "—"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function SelectionRow({ selection }: { selection: SkillSelection }) {
  return (
    <div className="bg-hermes-card border border-hermes-border/50 rounded-lg p-3 flex items-center gap-3">
      <div className="flex items-center gap-2 min-w-[120px]">
        <span className="text-sm font-medium text-hermes-text font-mono">{selection.skill_name}</span>
        <Badge variant={selection.score > 0.7 ? "success" : selection.score > 0.4 ? "warning" : "default"}>
          {(selection.score * 100).toFixed(0)}%
        </Badge>
      </div>
      <span className="text-[11px] text-hermes-muted flex-1">{selection.justification}</span>
    </div>
  );
}

function SkillCard({ skill }: { skill: Skill }) {
  return (
    <div className="bg-hermes-bg rounded-lg p-3 border border-hermes-border/50 hover:border-hermes-border transition-colors">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-hermes-text">{skill.name}</span>
        <Badge variant={skill.status === "ACTIVE" ? "success" : skill.status === "LOADED" ? "info" : "default"}>
          {skill.status}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-1 mb-2">
        {skill.tags?.slice(0, 4).map((tag) => (
          <span key={tag} className="text-[10px] text-hermes-muted font-mono">{tag}</span>
        ))}
      </div>
      {skill.metrics && (
        <div className="grid grid-cols-3 gap-1 text-[10px] font-mono">
          <span className="text-hermes-muted">Réussite :</span>
          <span className="col-span-2 text-hermes-text">{((skill.metrics?.success_rate || 0) * 100).toFixed(0)}%</span>
          <span className="text-hermes-muted">Mémoire :</span>
          <span className="col-span-2 text-hermes-text">{skill.metrics?.memory_mb || 0} MB</span>
        </div>
      )}
      {skill.dependencies?.length > 0 && (
        <div className="mt-1 text-[10px] text-hermes-muted font-mono">
          Dépendances : {skill.dependencies.join(", ")}
        </div>
      )}
    </div>
  );
}
