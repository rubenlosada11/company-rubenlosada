import { Audience } from "@/components/Audience";
import { Contact } from "@/components/Contact";
import { Coverage } from "@/components/Coverage";
import { Hero } from "@/components/Hero";
import { Process } from "@/components/Process";
import { Services } from "@/components/Services";
import { ValueProposition } from "@/components/ValueProposition";
import { WhyTrackFlow } from "@/components/WhyTrackFlow";

export default function HomePage() {
  return (
    <>
      <Hero />
      <ValueProposition />
      <Services />
      <Process />
      <Coverage />
      <WhyTrackFlow />
      <Audience />
      <Contact />
    </>
  );
}
