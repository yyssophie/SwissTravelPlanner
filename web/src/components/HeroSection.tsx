import { Link } from "react-router-dom";

const HeroSection = () => (
  <section className="hero" id="start">
    <div className="hero__overlay" />
    <div className="hero__content">
      <h1 className="hero__headline">Your Personalized Swiss Adventure, Designed by AI</h1>
      <div className="hero__actions">
        <Link className="btn btn--primary" to="/planner">Start planning now</Link>
      </div>
    </div>
  </section>
);

export default HeroSection;
