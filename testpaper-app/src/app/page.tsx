import Link from "next/link";
import {
  GraduationCap, ArrowRight, Upload, Layers, Wand2, ClipboardList,
  Download, ShieldCheck, Sparkles, BookOpen, CheckCircle2,
} from "lucide-react";

const features = [
  { icon: Upload, title: "Upload any textbook", body: "Drop a PDF — it's stored in your Google Drive and processed chapter-by-chapter automatically." },
  { icon: Layers, title: "Chapter-wise papers", body: "Pick the whole book or just the chapters you want the paper to cover." },
  { icon: Sparkles, title: "Difficulty by class", body: "Set the class standard and the question difficulty adapts automatically." },
  { icon: Wand2, title: "Auto or custom format", body: "Use the AI-suggested mix, or choose your own question types, counts and marks." },
  { icon: ClipboardList, title: "Full editor", body: "Edit any question, change marks, reorder or delete — before you export." },
  { icon: Download, title: "Preview & download", body: "See the finished paper, then download a clean, print-ready PDF." },
];

const steps = [
  { n: 1, title: "Upload a book", body: "Add a PDF textbook. We extract its chapters and index the content." },
  { n: 2, title: "Choose & configure", body: "Select the book, pick chapters, set the class standard and subject." },
  { n: 3, title: "Generate", body: "Let AI draft the questions, or define your own format." },
  { n: 4, title: "Edit & download", body: "Fine-tune every question, preview, and download the PDF." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <header className="sticky top-0 z-40 bg-white/80 backdrop-blur border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 flex items-center justify-center shadow-sm">
            <GraduationCap className="w-5 h-5 text-white" />
          </div>
          <p className="font-bold text-gray-900">Test Paper Generator</p>
          <Link href="/app"
            className="ml-auto flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold bg-brand-600 text-white hover:bg-brand-700 transition-colors">
            Open app <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-brand-50 to-white -z-10" />
        <div className="max-w-6xl mx-auto px-6 py-20 text-center">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-100 text-brand-700 text-xs font-medium mb-5">
            <Sparkles className="w-3.5 h-3.5" /> AI-powered question papers
          </span>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-gray-900 max-w-3xl mx-auto leading-tight">
            Turn any textbook into a{" "}
            <span className="bg-gradient-to-r from-brand-600 to-indigo-600 bg-clip-text text-transparent">
              ready-to-print question paper
            </span>
          </h1>
          <p className="mt-5 text-lg text-gray-600 max-w-2xl mx-auto">
            Upload a PDF, pick the chapters, set the class standard — and get a clean, chapter-wise test paper you can fully edit and download in minutes.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link href="/app"
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-base font-semibold bg-brand-600 text-white hover:bg-brand-700 shadow-sm transition-colors">
              Get started <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="#how"
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-base font-medium text-gray-700 border border-gray-300 hover:bg-gray-50 transition-colors">
              How it works
            </a>
          </div>
          <p className="mt-5 text-sm text-gray-400 flex items-center justify-center gap-1.5">
            <ShieldCheck className="w-4 h-4" /> No sign-up needed · books stored in your Google Drive
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-2xl sm:text-3xl font-bold text-center text-gray-900">Everything you need</h2>
        <p className="text-center text-gray-500 mt-2 mb-10">From raw PDF to a polished exam paper.</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((f) => (
            <div key={f.title} className="rounded-2xl border border-gray-200 p-6 hover:shadow-md hover:border-brand-200 transition-all bg-white">
              <div className="w-11 h-11 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600 mb-4">
                <f.icon className="w-5 h-5" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-1.5">{f.title}</h3>
              <p className="text-sm text-gray-600 leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="bg-slate-50 border-y border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-2xl sm:text-3xl font-bold text-center text-gray-900">How it works</h2>
          <p className="text-center text-gray-500 mt-2 mb-12">Four simple steps.</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((s) => (
              <div key={s.n} className="relative">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-sm">
                  {s.n}
                </div>
                <h3 className="font-semibold text-gray-900 mt-4 mb-1">{s.title}</h3>
                <p className="text-sm text-gray-600 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="rounded-3xl bg-gradient-to-r from-brand-600 to-indigo-600 px-8 py-12 text-center text-white shadow-sm">
          <BookOpen className="w-10 h-10 mx-auto mb-4 opacity-90" />
          <h2 className="text-2xl sm:text-3xl font-bold">Ready to make your first paper?</h2>
          <p className="text-white/85 mt-2 mb-7">It takes less than a minute to get started.</p>
          <Link href="/app"
            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl text-base font-semibold bg-white text-brand-700 hover:bg-brand-50 transition-colors">
            Start now <ArrowRight className="w-4 h-4" />
          </Link>
          <div className="flex items-center justify-center gap-6 mt-7 text-sm text-white/80 flex-wrap">
            {["No sign-up", "Any PDF textbook", "Edit before download"].map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-8 flex items-center gap-3 text-sm text-gray-500">
          <GraduationCap className="w-5 h-5 text-brand-600" />
          Test Paper Generator
          <span className="ml-auto">Built for teachers</span>
        </div>
      </footer>
    </div>
  );
}
