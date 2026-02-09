import { useParams, Navigate } from "react-router-dom";
import Header from "../components/Home/Header";
import TracksMain from "../components/Tracks/Main";
import Footer from "../components/Home/Footer";
import tracks from "../data/tracks";

export default function CourseDetailsPage() {
  const { courseid } = useParams<{ courseid: string }>();
  const track = tracks.find((t) => t.id === Number(courseid));

  if (!track) return <Navigate to="/tracks" replace />;

  return (
    <div className="bg-zinc-950 text-[#F0F0F0]">
      <Header />
      <TracksMain track={track} />
      <Footer />
    </div>
  );
}
