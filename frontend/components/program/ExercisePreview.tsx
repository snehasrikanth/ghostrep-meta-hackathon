"use client";

import { Card } from "@/components/ui/card";
import { ExerciseDemo } from "@/components/workout/ExerciseDemo";
import {
  exerciseDisplayName,
  formatExerciseDose,
  type WeightUnit,
} from "@/lib/training";
import type { WorkoutExercise } from "@/lib/types";

export function ExercisePreview({
  exercise,
  index,
  unit,
}: {
  exercise: WorkoutExercise;
  index: number;
  unit: WeightUnit;
}) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm uppercase text-white/80">
            {String(index + 1).padStart(2, "0")}
          </p>
          <div className="flex flex-wrap items-center gap-x-3">
          <h3 className="exercise-title text-xl font-medium">
            {exerciseDisplayName(exercise.exercise_id, exercise.name)}
          </h3>
          <ExerciseDemo exerciseId={exercise.exercise_id} />
          </div>
          {exercise.notes && (
            <p className="mt-1 max-w-xl text-sm leading-6 text-white/80">
              {exercise.notes}
            </p>
          )}
          {exercise.video_analysis && <p className="mt-2 text-sm font-medium text-teal">Video coaching available</p>}
        </div>
        <div className="text-right font-mono text-sm text-white/80">
          {formatExerciseDose(exercise, unit)}
          <div className="text-white/80">{exercise.rest_seconds}s rest</div>
        </div>
      </div>
    </Card>
  );
}
