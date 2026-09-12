import Link from "next/link";
import { ReportForm } from "@/components/report-form";
import { WORKFLOWS } from "@/src/catalog";

export default function HomePage() {
  return <main>
    <header className="masthead"><Link className="brand" href="/"><span>FADS</span> Road Response</Link><Link href="/dispatch">Dispatcher board</Link></header>
    <section className="hero">
      <div><p className="eyebrow">Municipal road maintenance</p><h1>Show us the damage.<br/>We’ll coordinate the response.</h1><p className="lede">Upload a photo, pin the location, and choose the closest issue. FADS builds a safe crew and equipment plan for dispatcher approval.</p></div>
      <div className="promise"><strong>What happens next</strong><ol><li>Report acknowledged in seconds</li><li>Evidence checked against an approved workflow</li><li>Available crew and equipment coordinated</li><li>Track progress with a private link</li></ol></div>
    </section>
    <section className="report-shell"><div className="section-heading"><p className="eyebrow">New road report</p><h2>Where should we send the crew?</h2></div><ReportForm workflows={Object.values(WORKFLOWS).map(({id,label,description})=>({id,label,description}))}/></section>
    <footer>Demo system — not an emergency dispatch service. For immediate danger, contact local emergency services.</footer>
  </main>;
}
