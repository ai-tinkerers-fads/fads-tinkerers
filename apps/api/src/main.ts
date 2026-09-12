import "reflect-metadata";
import {
  Body,
  Controller,
  Get,
  Headers,
  Inject,
  Module,
  Param,
  Post,
  ServiceUnavailableException,
  BadRequestException,
} from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import { json, type Request, type Response, type NextFunction } from "express";
import { AmbiguousService } from "./ambiguous.service";
import { SessionStore } from "./session-store";
import { Intake } from "./intake";
import { LiveService } from "./live.service";

export class SessionsService {
  readonly store = new SessionStore();
  readonly adapter = new AmbiguousService();
  readonly intake = new Intake(this.store, (draft, key) =>
    this.adapter.createTask(draft, key),
  );
  readonly live = new LiveService(this.store, this.intake);
  config() {
    return {
      liveAvailable:
        !!process.env.OPENAI_API_KEY &&
        (!!process.env.AMBIGUOUS_API_KEY ||
          process.env.AMBIGUOUS_MODE === "demo"),
      demoAvailable: true,
      recordMode: process.env.AMBIGUOUS_MODE === "demo" ? "demo" : "live",
    };
  }
}

@Controller("api")
class ApiController {
  constructor(
    @Inject(SessionsService) private readonly service: SessionsService,
  ) {}
  @Get("config") config() {
    return this.service.config();
  }
  @Post("sessions") async create(
    @Body() body: { mode?: string; sdp?: unknown },
  ) {
    if (!body || !["demo", "live"].includes(body.mode ?? ""))
      throw new BadRequestException("Choose demo or live mode");
    if (body.mode === "live" && !this.service.config().liveAvailable)
      throw new ServiceUnavailableException(
        "Configure OpenAI and Ambiguous.ai credentials on the backend before starting a live call.",
      );
    if (
      body.mode === "live" &&
      (typeof body.sdp !== "string" ||
        !body.sdp.startsWith("v=0") ||
        body.sdp.length > 60000)
    )
      throw new BadRequestException("A valid SDP offer is required");
    const { session, token } = this.service.store.create(
      body.mode as "demo" | "live",
    );
    if (session.mode === "demo") {
      this.service.intake.append(session, {
        id: "greeting",
        role: "assistant",
        text: "This is a text simulation: no microphone or external records are used. What road damage, repair complaint, or road-related question would you like to log?",
      });
      return { ...this.service.store.public(session), token };
    }
    const transport = await this.service.live.start(
      session,
      body.sdp as string,
    );
    return { ...this.service.store.public(session), token, transport };
  }
  @Get("sessions/:id") get(
    @Param("id") id: string,
    @Headers("authorization") auth?: string,
  ) {
    return this.service.store.public(this.service.store.authorized(id, auth));
  }
  @Post("sessions/:id/demo-message") async message(
    @Param("id") id: string,
    @Headers("authorization") auth: string,
    @Body() body: { text?: unknown },
  ) {
    const session = this.service.store.authorized(id, auth);
    if (typeof body?.text !== "string")
      throw new BadRequestException("Text is required");
    await this.service.intake.demoMessage(session, body.text);
    return this.service.store.public(session);
  }
  @Post("sessions/:id/end") end(
    @Param("id") id: string,
    @Headers("authorization") auth?: string,
  ) {
    const session = this.service.store.authorized(id, auth);
    this.service.live.end(session);
    return this.service.store.public(session);
  }
}

@Module({
  controllers: [ApiController],
  providers: [
    { provide: SessionsService, useFactory: () => new SessionsService() },
  ],
})
class AppModule {}

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  const origin = process.env.WEB_ORIGIN ?? "http://localhost:3000";
  app.use(json({ limit: "64kb" }));
  app.enableCors({
    origin,
    methods: ["GET", "POST"],
    allowedHeaders: ["Content-Type", "Authorization"],
  });
  // Local prototype only. CORS alone would not prevent a cross-origin paid session request.
  app.use((req: Request, res: Response, next: NextFunction) => {
    if (req.method === "POST" && req.headers.origin !== origin) {
      res.status(403).json({ message: "Unexpected request origin" });
      return;
    }
    res.setHeader("Cache-Control", "no-store");
    next();
  });
  await app.listen(Number(process.env.API_PORT ?? 3001), "127.0.0.1");
}
void bootstrap();
