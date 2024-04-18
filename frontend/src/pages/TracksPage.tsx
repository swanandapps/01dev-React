import Header from "../components/Home/Header";
import TracksList from "../components/Tracks/List";
import Footer from "../components/Home/Footer";

export default function TracksPage() {
  return (
    <div className="bg-zinc-950 text-[#F0F0F0]">
      <Header />
      <div className="pt-16">
        <TracksList />
      </div>
      <Footer />
    </div>
  );
}
