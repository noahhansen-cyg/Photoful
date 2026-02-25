import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import TV from "./pages/TV";
import Phone from "./pages/Phone";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/room/:code/tv" element={<TV />} />
        <Route path="/room/:code/phone" element={<Phone />} />
      </Routes>
    </BrowserRouter>
  );
}
