import type { CrewMember } from "@/src/contracts";

export const CREW: readonly Omit<CrewMember, "busy">[] = [
  {
    id: "0d65f104-e75e-4193-be7e-73e1bee754f4",
    name: "Aditya Indoori",
    skills: ["site_safety", "pothole_repair"],
    distanceKm: 2.4,
  },
  {
    id: "ccb878fe-4020-43e1-b641-a7c2642da4a0",
    name: "Felix Deschamps",
    skills: ["chainsaw", "pothole_repair", "site_safety"],
    distanceKm: 4.1,
  },
  {
    id: "3cfb4019-f3cf-4478-a41a-2e7540960baa",
    name: "Duc Minh Vo",
    skills: ["loader", "recovery", "site_safety"],
    distanceKm: 3.2,
  },
  {
    id: "8d8eeaef-34bf-41e6-a179-fac87ff92e0d",
    name: "Sanjana Upadhyaya",
    skills: ["transport", "disposal", "site_safety"],
    distanceKm: 5.0,
  },
];
