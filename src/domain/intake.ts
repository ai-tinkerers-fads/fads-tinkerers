import { z } from "zod";
import { ISSUE_TYPES, type ResidentReportInput } from "@/src/contracts";

export const reportFieldsSchema = z.object({
  residentName: z.string().trim().min(2).max(120),
  residentEmail: z.email().max(254),
  residentPhone: z.string().trim().min(7).max(30),
  issueType: z.enum(ISSUE_TYPES),
  address: z.string().trim().min(3).max(300),
  latitude: z.coerce.number().min(-90).max(90),
  longitude: z.coerce.number().min(-180).max(180),
  description: z.string().trim().max(2000).optional(),
});

export function validateReportForm(form: FormData): { report: ResidentReportInput; image: File } {
  const fields = reportFieldsSchema.parse({
    residentName: form.get("residentName"),
    residentEmail: form.get("residentEmail"),
    residentPhone: form.get("residentPhone"),
    issueType: form.get("issueType"),
    address: form.get("address"),
    latitude: form.get("latitude"),
    longitude: form.get("longitude"),
    description: form.get("description") || undefined,
  });
  const image = form.get("image");
  if (!(image instanceof File) || image.size === 0) throw new Error("A road-damage image is required.");
  if (!image.type.startsWith("image/")) throw new Error("The uploaded file must be an image.");
  if (image.size > 10 * 1024 * 1024) throw new Error("The image must be 10 MB or smaller.");
  return {
    report: {
      ...fields,
      imageName: image.name || "road-damage.jpg",
      imageMimeType: image.type,
    },
    image,
  };
}
