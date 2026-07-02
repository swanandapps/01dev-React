import { useNavigate } from "react-router-dom";
import Header from "../components/Home/Header";
import { NotesQuizModal } from "../components/learn/NotesQuizModal";

export default function NotesQuizPage() {
  const navigate = useNavigate();
  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="pt-24 pb-12 flex justify-center px-4">
        <NotesQuizModal variant="page" onClose={() => navigate(-1)} />
      </div>
    </div>
  );
}
