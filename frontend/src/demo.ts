import fixture from './demo-fixture.json';
import { ApiError } from './api';
import { detailSchema, modelSchema, slateSchema, type Detail } from './contracts';

export const DEMO_DATE = fixture.slate.date;
const slate = slateSchema.parse(fixture.slate);
const details = fixture.details as Record<string, unknown>;
export const demo = {
  slate: async (date: string) =>
    date === DEMO_DATE ? slate : { ...slate, date, count: 0, predictions: [] },
  detail: async (id: number): Promise<Detail> => {
    if (!details[String(id)])
      throw new ApiError('No demonstration game was found. Try 8000001, 8000002, or 8000003.', 404);
    return detailSchema.parse(details[String(id)]);
  },
  model: async () => modelSchema.parse(fixture.model),
};
