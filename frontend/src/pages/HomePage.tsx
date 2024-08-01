import Header from "../components/Home/Header";
import Banner from "../components/Home/Banner";
import Banner2 from "../components/Home/Banner2";
import Footer from "../components/Home/Footer";

export default function HomePage() {
  return (
    <div className="bg-zinc-950 text-[#F0F0F0]">
      <Header />
      <Banner />
      <Banner2 />
      <Footer />
    </div>
  );
}
