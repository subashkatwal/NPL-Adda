import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <section className="page">
      <h1>Out of the ground.</h1>
      <p className="lede">That page doesn't exist.</p>
      <Link className="btn" to="/">Back home</Link>
    </section>
  );
}
