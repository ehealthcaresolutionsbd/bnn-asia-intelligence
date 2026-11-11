<?php
/** Country profile page served at /{country_base}/{slug}/ inside the active theme. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
get_header();
?>
<main id="primary" class="site-main bnn-intel-page">
	<?php echo BNN_Intel_Public::render( 'country', array( 'slug' => sanitize_title( get_query_var( 'bnn_country' ) ) ) ); // phpcs:ignore ?>
</main>
<?php
get_footer();
